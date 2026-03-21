//
//  ContentView.swift
//  PredictMyFuture
//
//  Created by Aden  Al-Hardan on 3/21/26.
//

import AVFoundation
import Combine
import SwiftUI
import UIKit

private enum AppConfig {
    static let apiBaseURL = URL(string: "https://predictmyfuture.backsellai.com")!
}

struct ContentView: View {
    @StateObject private var recorder = CameraRecorder(apiClient: APIClient(baseURL: AppConfig.apiBaseURL))

    var body: some View {
        ZStack {
            CameraPreviewView(session: recorder.session)
                .ignoresSafeArea()
                .opacity(recorder.isShowingLoadingScreen ? 0.18 : 1)

            VStack {
                HStack {
                    Text(recorder.statusMessage)
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(.black.opacity(0.65), in: Capsule())

                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.top, 18)

                Spacer()

                if !recorder.isShowingLoadingScreen {
                    Button(action: recorder.recordButtonTapped) {
                        ZStack {
                            Circle()
                                .fill(.white)
                                .frame(width: 84, height: 84)

                            if recorder.isBusy {
                                ProgressView()
                                    .tint(.black)
                            } else if recorder.isRecording {
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(.red)
                                    .frame(width: 30, height: 30)
                            } else {
                                Circle()
                                    .fill(.red)
                                    .frame(width: 64, height: 64)
                            }
                        }
                    }
                    .disabled(!recorder.isReady || recorder.isBusy)
                    .padding(.bottom, 40)
                }
            }

            if recorder.isShowingLoadingScreen {
                LoadingOverlay(
                    statusMessage: recorder.statusMessage,
                    pollResultText: recorder.pollResultText
                )
                    .transition(.opacity)
            }
        }
        .background(.black)
        .animation(.easeInOut(duration: 0.2), value: recorder.isShowingLoadingScreen)
        .task {
            await recorder.configureIfNeeded()
        }
        .alert("Recording Error", isPresented: errorBinding) {
            Button("OK", role: .cancel) {
                recorder.errorMessage = nil
            }
        } message: {
            Text(recorder.errorMessage ?? "Something went wrong.")
        }
    }

    private var errorBinding: Binding<Bool> {
        Binding(
            get: { recorder.errorMessage != nil },
            set: { isPresented in
                if !isPresented {
                    recorder.errorMessage = nil
                }
            }
        )
    }
}

private struct LoadingOverlay: View {
    let statusMessage: String
    let pollResultText: String?

    var body: some View {
        ZStack {
            Color.black.opacity(0.72)
                .ignoresSafeArea()

            VStack(spacing: 18) {
                ProgressView()
                    .scaleEffect(1.4)
                    .tint(.white)

                Text("Processing your video")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white)

                Text(statusMessage)
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)

                if let pollResultText, !pollResultText.isEmpty {
                    ScrollView {
                        Text(pollResultText)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.white.opacity(0.9))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(14)
                    }
                    .frame(maxHeight: 220)
                    .background(.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
            }
            .padding(28)
            .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .stroke(.white.opacity(0.12), lineWidth: 1)
            )
            .padding(.horizontal, 28)
        }
    }
}

struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.videoGravity = .resizeAspectFill
        view.previewLayer.session = session
        return view
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {
        uiView.previewLayer.session = session
    }
}

final class PreviewView: UIView {
    override class var layerClass: AnyClass {
        AVCaptureVideoPreviewLayer.self
    }

    var previewLayer: AVCaptureVideoPreviewLayer {
        guard let layer = layer as? AVCaptureVideoPreviewLayer else {
            fatalError("Expected AVCaptureVideoPreviewLayer")
        }
        return layer
    }
}

@MainActor
final class CameraRecorder: NSObject, ObservableObject {
    @Published var errorMessage: String?
    @Published private(set) var isBusy = false
    @Published private(set) var isReady = false
    @Published private(set) var isRecording = false
    @Published private(set) var isShowingLoadingScreen = false
    @Published private(set) var statusMessage = "Preparing camera..."
    @Published private(set) var pollResultText: String?
    @Published private(set) var currentJobID: String?

    nonisolated(unsafe) let session = AVCaptureSession()

    private let apiClient: APIClient
    nonisolated(unsafe) private let movieOutput = AVCaptureMovieFileOutput()
    private let sessionQueue = DispatchQueue(label: "predictmyfuture.camera.session")

    private var configuredSession = false
    private var currentRecordingContinuation: CheckedContinuation<URL, Error>?

    init(apiClient: APIClient) {
        self.apiClient = apiClient
        super.init()
    }

    func configureIfNeeded() async {
        guard !configuredSession else { return }
        configuredSession = true

        do {
            let permissionsGranted = try await requestPermissions()
            guard permissionsGranted else {
                throw CameraRecorderError.permissionsDenied
            }

            try await configureSession()
            statusMessage = "Ready to record"
            isReady = true
        } catch {
            errorMessage = error.localizedDescription
            statusMessage = "Camera unavailable"
            isReady = false
        }
    }

    func recordButtonTapped() {
        guard !isBusy else { return }

        if isRecording {
            Task {
                await finishRecordingAndUpload()
            }
        } else {
            startRecording()
        }
    }

    private func startRecording() {
        guard isReady else { return }

        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("mov")

        try? FileManager.default.removeItem(at: outputURL)

        currentJobID = nil
        pollResultText = nil
        statusMessage = "Recording..."
        isRecording = true

        sessionQueue.async {
            self.movieOutput.startRecording(to: outputURL, recordingDelegate: self)
        }
    }

    private func finishRecordingAndUpload() async {
        isBusy = true
        isShowingLoadingScreen = true
        currentJobID = nil
        pollResultText = nil
        statusMessage = "Finishing recording..."

        do {
            let movURL = try await stopRecording()
            statusMessage = "Converting to mp4..."

            let mp4URL = try await convertToMP4(sourceURL: movURL)
            try? FileManager.default.removeItem(at: movURL)

            statusMessage = "Requesting upload URL..."
            let uploadInfo = try await apiClient.fetchPresignedUploadURL(
                filename: mp4URL.lastPathComponent,
                contentType: "video/mp4"
            )

            statusMessage = "Uploading video..."
            try await apiClient.uploadVideo(fileURL: mp4URL, to: uploadInfo.uploadURL)
            try? FileManager.default.removeItem(at: mp4URL)

            if let jobID = uploadInfo.jobID, !jobID.isEmpty {
                currentJobID = jobID
                statusMessage = "Upload complete. Starting prediction..."
                try await apiClient.startPrediction(jobID: jobID)

                statusMessage = "Prediction started. Checking job status..."
                let finalResult = try await apiClient.pollJobStatus(jobID: currentJobID ?? jobID) { result in
                    Task { @MainActor in
                        self.pollResultText = result
                    }
                }
                pollResultText = finalResult
                statusMessage = "Prediction complete"
                isShowingLoadingScreen = false
            } else {
                statusMessage = "Upload complete"
            }
        } catch {
            errorMessage = error.localizedDescription
            statusMessage = "Upload failed"
            isShowingLoadingScreen = false
        }

        isBusy = false
    }

    private func stopRecording() async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            currentRecordingContinuation = continuation
            sessionQueue.async {
                self.movieOutput.stopRecording()
            }
        }
    }

    private func configureSession() async throws {
        try await withCheckedThrowingContinuation { continuation in
            sessionQueue.async {
                do {
                    self.session.beginConfiguration()
                    self.session.sessionPreset = .high

                    self.session.inputs.forEach { self.session.removeInput($0) }
                    self.session.outputs.forEach { self.session.removeOutput($0) }

                    guard
                        let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
                    else {
                        throw CameraRecorderError.cameraUnavailable
                    }

                    let videoInput = try AVCaptureDeviceInput(device: camera)
                    guard self.session.canAddInput(videoInput) else {
                        throw CameraRecorderError.cameraUnavailable
                    }
                    self.session.addInput(videoInput)

                    if let microphone = AVCaptureDevice.default(for: .audio) {
                        let audioInput = try AVCaptureDeviceInput(device: microphone)
                        if self.session.canAddInput(audioInput) {
                            self.session.addInput(audioInput)
                        }
                    }

                    guard self.session.canAddOutput(self.movieOutput) else {
                        throw CameraRecorderError.cameraUnavailable
                    }
                    self.session.addOutput(self.movieOutput)
                    self.movieOutput.movieFragmentInterval = .invalid

                    self.session.commitConfiguration()

                    if !self.session.isRunning {
                        self.session.startRunning()
                    }

                    continuation.resume()
                } catch {
                    self.session.commitConfiguration()
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func requestPermissions() async throws -> Bool {
        let videoGranted = try await requestAccess(for: .video)
        let audioGranted = try await requestAccess(for: .audio)
        return videoGranted && audioGranted
    }

    private func requestAccess(for mediaType: AVMediaType) async throws -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: mediaType) {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: mediaType)
        case .denied, .restricted:
            return false
        @unknown default:
            return false
        }
    }

    private func convertToMP4(sourceURL: URL) async throws -> URL {
        let destinationURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("mp4")

        try? FileManager.default.removeItem(at: destinationURL)

        let asset = AVURLAsset(url: sourceURL)
        guard let exportSession = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetHighestQuality) else {
            throw CameraRecorderError.exportFailed
        }

        exportSession.outputURL = destinationURL
        exportSession.outputFileType = .mp4
        exportSession.shouldOptimizeForNetworkUse = true

        do {
            try await exportSession.export(to: destinationURL, as: .mp4)
            return destinationURL
        } catch is CancellationError {
            throw CameraRecorderError.exportCancelled
        } catch {
            throw error
        }
    }
}

extension CameraRecorder: AVCaptureFileOutputRecordingDelegate {
    nonisolated func fileOutput(
        _ output: AVCaptureFileOutput,
        didFinishRecordingTo outputFileURL: URL,
        from connections: [AVCaptureConnection],
        error: Error?
    ) {
        Task { @MainActor in
            let continuation = currentRecordingContinuation
            currentRecordingContinuation = nil
            isRecording = false

            if let error {
                continuation?.resume(throwing: error)
            } else {
                continuation?.resume(returning: outputFileURL)
            }
        }
    }
}

struct APIClient {
    let baseURL: URL

    func fetchPresignedUploadURL(filename: String, contentType: String) async throws -> PresignedUploadInfo {
        var components = URLComponents(url: baseURL.appending(path: "/api/get-presigned-url"), resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "filename", value: filename),
            URLQueryItem(name: "content_type", value: contentType),
        ]

        guard let url = components?.url else {
            throw APIClientError.invalidEndpoint
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)

        return try decodeUploadInfo(from: data)
    }

    func uploadVideo(fileURL: URL, to uploadURL: URL) async throws {
        var request = URLRequest(url: uploadURL)
        request.httpMethod = "PUT"
        request.setValue("video/mp4", forHTTPHeaderField: "Content-Type")

        let (_, response) = try await URLSession.shared.upload(for: request, fromFile: fileURL)
        try validate(response: response, data: nil)
    }

    func startPrediction(jobID: String) async throws {
        let url = baseURL.appending(path: "/api/predict/start")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["job_id": jobID])

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)
    }

    func pollJobStatus(
        jobID: String,
        onStatusUpdate: @escaping @Sendable (String) -> Void
    ) async throws -> String {
        while true {
            let response = try await fetchJobStatus(jobID: jobID)
            onStatusUpdate(response.rawText)

            if response.status?.caseInsensitiveCompare("processing") != .orderedSame {
                print(response.rawText)
                return response.rawText
            }

            try await Task.sleep(for: .seconds(2))
        }
    }

    private func fetchJobStatus(jobID: String) async throws -> PollResponse {
        var components = URLComponents(url: baseURL.appending(path: "/api/poll"), resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "job_id", value: jobID),
        ]

        guard let url = components?.url else {
            throw APIClientError.invalidEndpoint
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)
        try validate(response: response, data: data)

        return try decodePollResponse(from: data)
    }

    private func decodeUploadInfo(from data: Data) throws -> PresignedUploadInfo {
        if let rawString = String(data: data, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
           let url = URL(string: rawString),
           rawString.hasPrefix("http") {
            return PresignedUploadInfo(uploadURL: url, jobID: nil)
        }

        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIClientError.invalidResponse
        }

        let possibleURLKeys = ["upload_url", "presigned_url", "url", "uploadUrl", "presignedUrl"]
        let uploadURLString = possibleURLKeys
            .compactMap { object[$0] as? String }
            .first

        guard let uploadURLString, let uploadURL = URL(string: uploadURLString) else {
            throw APIClientError.invalidResponse
        }

        let possibleJobKeys = ["job_id", "jobId"]
        let jobID = possibleJobKeys
            .compactMap { object[$0] as? String }
            .first

        return PresignedUploadInfo(uploadURL: uploadURL, jobID: jobID)
    }

    private func decodePollResponse(from data: Data) throws -> PollResponse {
        if let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
           JSONSerialization.isValidJSONObject(object),
           let prettyData = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted]),
           let prettyText = String(data: prettyData, encoding: .utf8) {
            let status = object["status"] as? String
            return PollResponse(rawText: prettyText, status: status)
        }

        if let rawText = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !rawText.isEmpty {
            return PollResponse(rawText: rawText, status: nil)
        }

        throw APIClientError.invalidResponse
    }

    private func validate(response: URLResponse, data: Data?) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if let data, let serverMessage = String(data: data, encoding: .utf8), !serverMessage.isEmpty {
                throw APIClientError.serverError(serverMessage)
            }
            throw APIClientError.httpStatus(httpResponse.statusCode)
        }
    }
}

struct PresignedUploadInfo {
    let uploadURL: URL
    let jobID: String?
}

struct PollResponse {
    let rawText: String
    let status: String?
}

enum CameraRecorderError: LocalizedError {
    case cameraUnavailable
    case exportCancelled
    case exportFailed
    case permissionsDenied

    var errorDescription: String? {
        switch self {
        case .cameraUnavailable:
            return "The camera could not be configured on this device."
        case .exportCancelled:
            return "The mp4 conversion was cancelled."
        case .exportFailed:
            return "The recording could not be converted to mp4."
        case .permissionsDenied:
            return "Camera and microphone access are required."
        }
    }
}

enum APIClientError: LocalizedError {
    case httpStatus(Int)
    case invalidEndpoint
    case invalidResponse
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .httpStatus(let statusCode):
            return "Request failed with status code \(statusCode)."
        case .invalidEndpoint:
            return "The upload endpoint is invalid."
        case .invalidResponse:
            return "The server returned an unexpected presigned URL response."
        case .serverError(let message):
            return message
        }
    }
}

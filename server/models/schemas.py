from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


class SceneAnalysis(BaseModel):
    people: str
    actions: str
    setting: str
    mood: str
    key_objects: str


class ScenarioPrompt(BaseModel):
    type: Literal["positive", "bad", "insane", "funny"]
    title: str
    description: str
    visual_description: str


class ScenarioPrompts(BaseModel):
    scenarios: list[ScenarioPrompt]


class Scenario(BaseModel):
    type: Literal["positive", "bad", "insane", "funny"]
    title: str
    description: str
    video_url: str


class PredictionResponse(BaseModel):
    id: str
    scene_analysis: str
    scenarios: list[Scenario]


class JobStatus(BaseModel):
    status: Literal["pending", "processing", "completed", "failed"]
    prediction: Optional[PredictionResponse] = None
    error: Optional[str] = None

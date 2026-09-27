import reflex as rx

from app.components.deepshield.contracts import Contract, Field
from app.components.deepshield.datasets.robustness import Augmentation


class TrainingConfig(Contract):
    dataset_root: str
    manifest: str
    output: str
    pretrained: str = ""
    factory: str = "app.components.deepshield.training.transfer:build"
    seed: int = 42
    epochs: int = Field(default=15, ge=1, le=1000)
    batch_size: int = Field(default=4, ge=1, le=128)
    learning_rate: float = Field(default=0.0001, gt=0)
    patience: int = Field(default=4, ge=1)
    min_delta: float = Field(default=0.0001, ge=0)
    weight_decay: float = Field(default=0.01, ge=0)
    balance_classes: bool = True
    freeze_backbone: bool = True
    max_text_tokens: int = Field(default=256, ge=32, le=512)
    fusion_features: int = Field(default=20, ge=1)
    augmentation: Augmentation = Field(default_factory=Augmentation)
    threshold: float = Field(default=0.5, ge=0, le=1)
    threshold_validation_id: str = ""
    feature_manifest_id: str = ""

import reflex as rx

from pathlib import Path


def build(modality, config):
    """Return model, input encoder, batch collator, provenance. No implicit downloads."""
    import torch
    import numpy as np
    from torch import nn
    from torch.utils.data._utils.collate import default_collate

    if modality == "text":
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
        )

        if not config.pretrained:
            raise ValueError(
                "Text transfer learning needs a local reviewed multilingual backbone"
            )
        tokenizer = AutoTokenizer.from_pretrained(
            config.pretrained, local_files_only=True, trust_remote_code=False
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            config.pretrained,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            num_labels=2,
            ignore_mismatched_sizes=True,
        )
        if config.freeze_backbone:
            for parameter in model.base_model.parameters():
                parameter.requires_grad = False

        class BinaryText(nn.Module):
            def __init__(self, classifier):
                super().__init__()
                self.classifier = classifier

            def forward(self, batch):
                logits = self.classifier(**batch).logits
                return logits[:, 1] - logits[:, 0]

        def collate(rows):
            texts, labels = zip(*rows)
            return tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=config.max_text_tokens,
                return_tensors="pt",
            ), torch.tensor(labels, dtype=torch.float32)

        return (
            BinaryText(model),
            lambda value: value,
            collate,
            {
                "architecture": "multilingual_sequence_classifier",
                "preprocessing": "original-language-tokenization",
            },
        )
    if modality == "multimodal":
        if not config.feature_manifest_id:
            raise ValueError(
                "Stacking training requires out-of-fold feature manifest identity"
            )

        class Stacker(nn.Module):
            def __init__(self):
                super().__init__()
                self.linear = nn.Linear(config.fusion_features, 1)

            def forward(self, features):
                return self.linear(features).squeeze(-1)

        def encode_features(value):
            if (
                len(value) != config.fusion_features
                or not np.isfinite(value).all()
            ):
                raise ValueError("Invalid ordered stacking feature vector")
            return torch.tensor(value, dtype=torch.float32)

        return (
            Stacker(),
            encode_features,
            default_collate,
            {
                "architecture": "logistic_stacker",
                "feature_manifest_id": config.feature_manifest_id,
            },
        )

    from torchvision.models import mobilenet_v3_small
    from torchvision.transforms import Compose, Resize, ToTensor, Normalize

    backbone = mobilenet_v3_small(weights=None)
    if not config.pretrained:
        raise ValueError(
            "Transfer learning requires approved local MobileNetV3-small state_dict"
        )
    path = Path(config.pretrained)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Backbone exceeds CPU transfer-learning budget")
    backbone.load_state_dict(
        torch.load(path, map_location="cpu", weights_only=True)
    )
    features = backbone.features
    if config.freeze_backbone:
        for parameter in features.parameters():
            parameter.requires_grad = False

    class Detector(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = features
            self.temporal = (
                nn.GRU(576, 64, batch_first=True)
                if modality == "video"
                else None
            )
            self.head = nn.Linear(64 if modality == "video" else 576, 1)

        def forward(self, inputs):
            if self.temporal is not None:
                batch, frames, channels, height, width = inputs.shape
                encoded = self.features(
                    inputs.reshape(batch * frames, channels, height, width)
                ).mean(dim=(-2, -1))
                _, hidden = self.temporal(encoded.reshape(batch, frames, 576))
                return self.head(hidden[-1]).squeeze(-1)
            encoded = self.features(inputs).mean(dim=(-2, -1))
            return self.head(encoded).squeeze(-1)

    image_transform = Compose(
        [
            Resize((224, 224)),
            ToTensor(),
            Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    def encode(value):
        if modality == "video":
            return torch.stack([image_transform(frame) for frame in value])
        if modality == "audio":
            import librosa
            import torch.nn.functional as functional

            mel = librosa.power_to_db(
                librosa.feature.melspectrogram(y=value, sr=16000, n_mels=64),
                ref=np.max,
            )
            tensor = torch.tensor((mel + 80) / 80, dtype=torch.float32)[
                None, None
            ]
            return functional.interpolate(
                tensor, size=(224, 224), mode="bilinear", align_corners=False
            )[0].repeat(3, 1, 1)
        return image_transform(value)

    return (
        Detector(),
        encode,
        default_collate,
        {
            "architecture": "mobilenetv3_gru"
            if modality == "video"
            else "mobilenetv3_binary",
            "preprocessing": "8-uniform-frames"
            if modality == "video"
            else "log-mel64-resize224"
            if modality == "audio"
            else "imagenet-normalized-resize224",
            "scope": "team_checkpoint_not_public_baseline",
        },
    )

import reflex as rx

import logging
from app.components.deepshield.contracts import Evidence, Result
from app.components.deepshield.media import decode_audio
from app.components.deepshield.registry import Registry


class AudioService:
    def __init__(self, registry: Registry):
        self.registry = registry

    def detect(self, data: bytes, language: str = "auto") -> Result:
        import numpy as np
        import librosa

        waveform = decode_audio(data, self.registry.settings)
        silence = float(np.mean(np.abs(waveform) < 0.005))
        clipping = float(np.mean(np.abs(waveform) >= 0.999))
        quality = {
            "duration_seconds": len(waveform) / 16000,
            "silence_ratio": silence,
            "clipping_ratio": clipping,
            "rms": float(np.sqrt(np.mean(waveform**2))),
            "reliability": max(0.0, (1 - silence) * (1 - clipping)),
        }
        stride = max(1, len(waveform) // 512)
        mel = librosa.power_to_db(
            librosa.feature.melspectrogram(
                y=waveform,
                sr=16000,
                n_mels=40,
                n_fft=512,
                hop_length=max(160, len(waveform) // 256),
            ),
            ref=np.max,
        )
        evidence = [
            Evidence(
                kind="waveform",
                data={
                    "sample_rate": 16000,
                    "stride_samples": stride,
                    "values": waveform[::stride][:513].tolist(),
                },
            ),
            Evidence(
                kind="log_mel",
                data={
                    "db": mel[:, :257].tolist(),
                    "sample_rate": 16000,
                    "n_fft": 512,
                    "hop_length": max(160, len(waveform) // 256),
                    "scope": "signal_visualization_not_model_attribution",
                },
            ),
        ]
        if quality["rms"] < 0.00001:
            return Result(
                modality="audio",
                status="invalid_input",
                reason="silent_audio",
                quality=quality,
                evidence=evidence,
            )
        try:
            baseline = self.registry.available_baseline("audio")
            if baseline is None:
                return Result(
                    modality="audio",
                    reason="audio_checkpoint_unavailable_or_incompatible",
                    quality=quality,
                    evidence=evidence,
                )
            session, provenance = baseline
            scores = []
            windows = list(range(0, len(waveform), 48000))[
                : self.registry.settings.max_audio_windows
            ]
            for start in windows:
                chunk = waveform[start : start + 48000]
                padded = np.pad(chunk, (0, 48000 - len(chunk)))
                normalized = (
                    (padded - padded.mean()) / np.sqrt(padded.var() + 1e-5)
                ).astype(np.float32)[None]
                logits = np.asarray(
                    session.run(
                        None, {session.get_inputs()[0].name: normalized}
                    )[0]
                )
                if logits.shape != (1, 2) or not np.isfinite(logits).all():
                    raise ValueError("Expected finite binary logits")
                exponent = np.exp(logits - logits.max(axis=1, keepdims=True))
                score = float(
                    (exponent / exponent.sum(axis=1, keepdims=True))[0, 1]
                )
                scores.append(score)
                evidence.append(
                    Evidence(
                        kind="audio_window",
                        start_ms=start // 16,
                        end_ms=min(start + 48000, len(waveform)) // 16,
                        score=score,
                        data={"padded_samples": 48000 - len(chunk)},
                    )
                )
            ranked = sorted(
                [e for e in evidence if e.kind == "audio_window"],
                key=lambda e: e.score,
                reverse=True,
            )[:3]
            evidence.append(
                Evidence(
                    kind="highest_score_segments",
                    data={
                        "segments": [
                            {
                                "start_ms": e.start_ms,
                                "end_ms": e.end_ms,
                                "score": e.score,
                            }
                            for e in ranked
                        ],
                        "scope": "relative_ranking_not_validated_threshold",
                    },
                )
            )
            quality["window_disagreement"] = float(np.std(scores))
            warnings = [
                "Uncalibrated anti-spoofing evidence; not speaker identity verification.",
                "Noise, codecs, and unseen generators can change scores.",
            ]
            degraded = (
                quality["reliability"] < 0.5
                or language not in provenance.language_scope
                or len(waveform) < 48000
            )
            if language not in provenance.language_scope:
                warnings.append(
                    "Audio language unverified or outside validated five-language model scope; no speech-language detector is claimed."
                )
            return Result(
                modality="audio",
                status="degraded" if degraded else "ok",
                score=float(np.median(scores)),
                score_semantics="median_uncalibrated_synthetic_speech_score",
                provenance=provenance,
                quality=quality,
                evidence=evidence,
                warnings=warnings,
                language=language if language != "auto" else "und",
            )
        except Exception as e:
            logging.exception(f"Unexpected audio detection failure: {e}")
            return Result(
                modality="audio",
                reason="audio_checkpoint_unavailable_or_incompatible",
                quality=quality,
                evidence=evidence,
            )

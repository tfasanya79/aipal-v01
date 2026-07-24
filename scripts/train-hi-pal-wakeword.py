#!/usr/bin/env python3
"""Train a minimal openWakeWord-compatible hi_pal_v0.1.onnx model (Apache-2.0 toolchain).

Use a dedicated training venv (e.g. apps/api/.venv-train) with torch/openwakeword.
Do not install training deps into apps/api/.venv — that venv is for API pytest/deploy only.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "apps/mobile/assets/models"
VENV = ROOT / "apps/api/.venv"

sys.path.insert(0, str(VENV / "lib/python3.12/site-packages"))

from openwakeword.utils import AudioFeatures  # noqa: E402

PHRASE = "hi pal"
NEGATIVE_PHRASES = [
    "hello there",
    "hey jarvis",
    "hi paul",
    "high pal",
    "my pal",
    "bye pal",
    "help me",
    "good morning",
    "what time is it",
    "turn on the lights",
]
N_POS = 400
N_NEG = 800
CLIP_SAMPLES = 16000 * 2  # 2 s @ 16 kHz
N_FRAMES = 16
EMBED_DIM = 96


def espeak_wav(text: str, out: Path, speed: int = 175, pitch: int = 50) -> None:
    subprocess.run(
        [
            "espeak-ng",
            "-v",
            "en-us",
            "-s",
            str(speed),
            "-p",
            str(pitch),
            "-w",
            str(out),
            text,
        ],
        check=True,
        capture_output=True,
    )
    # Resample to 16 kHz mono via ffmpeg
    tmp = out.with_suffix(".tmp.wav")
    out.rename(tmp)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp), "-ar", "16000", "-ac", "1", str(out)],
        check=True,
        capture_output=True,
    )
    tmp.unlink(missing_ok=True)


def load_wav_int16(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16)


def pad_clip(audio: np.ndarray) -> np.ndarray:
    if len(audio) >= CLIP_SAMPLES:
        start = max(0, (len(audio) - CLIP_SAMPLES) // 2)
        return audio[start : start + CLIP_SAMPLES]
    out = np.zeros(CLIP_SAMPLES, dtype=np.int16)
    out[: len(audio)] = audio
    return out


def noise_clip() -> np.ndarray:
    return (np.random.randn(CLIP_SAMPLES) * 1200).astype(np.int16)


def make_features() -> AudioFeatures:
    model_dir = VENV / "lib/python3.12/site-packages/openwakeword/resources/models"
    return AudioFeatures(
        melspec_onnx_model_path=str(model_dir / "melspectrogram.onnx"),
        embedding_onnx_model_path=str(model_dir / "embedding_model.onnx"),
    )


def streaming_feature_windows(clip: np.ndarray, positive: bool) -> list[tuple[np.ndarray, float]]:
    """Extract (feature, label) pairs using the same streaming path as on-device inference."""
    fe = make_features()
    padded = np.concatenate(
        (np.zeros(16000, dtype=np.int16), clip, np.zeros(16000, dtype=np.int16))
    )

    samples: list[tuple[np.ndarray, float]] = []
    chunk = 1280
    n_chunks = max(1, (len(padded) - chunk) // chunk)
    # Positive label on middle third of original clip (after 1s pad)
    pos_start = 16000 + max(0, (len(clip) - CLIP_SAMPLES // 2) // 2)
    pos_end = pos_start + len(clip) // 2

    for i in range(0, len(padded) - chunk, chunk):
        frame = padded[i : i + chunk]
        fe(frame)
        if fe.feature_buffer.shape[0] < N_FRAMES:
            continue
        feat = fe.get_features(N_FRAMES).squeeze(0).astype(np.float32)
        sample_idx = i + chunk // 2
        label = 1.0 if positive and pos_start <= sample_idx <= pos_end else 0.0
        samples.append((feat, label))
    return samples


class WakeNet(nn.Module):
    def __init__(self, layer_dim: int = 32) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(N_FRAMES * EMBED_DIM, layer_dim),
            nn.LayerNorm(layer_dim),
            nn.ReLU(),
            nn.Linear(layer_dim, layer_dim),
            nn.LayerNorm(layer_dim),
            nn.ReLU(),
            nn.Linear(layer_dim, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def main() -> None:
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)

    model_dir = VENV / "lib/python3.12/site-packages/openwakeword/resources/models"

    samples: list[tuple[np.ndarray, float]] = []

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i in range(N_POS):
            wav = tmp / f"pos_{i}.wav"
            speed = random.randint(140, 210)
            pitch = random.randint(30, 70)
            espeak_wav(PHRASE, wav, speed=speed, pitch=pitch)
            clip = pad_clip(load_wav_int16(wav))
            samples.extend(streaming_feature_windows(clip, positive=True))

        for i in range(N_NEG):
            if i % 4 == 0:
                clip = noise_clip()
            else:
                phrase = random.choice(NEGATIVE_PHRASES)
                wav = tmp / f"neg_{i}.wav"
                espeak_wav(phrase, wav, speed=random.randint(150, 200), pitch=random.randint(35, 65))
                clip = pad_clip(load_wav_int16(wav))
            samples.extend(streaming_feature_windows(clip, positive=False))

    pos_count = sum(1 for _, y in samples if y >= 0.5)
    neg_count = len(samples) - pos_count
    print(f"Streaming samples: {pos_count} positive, {neg_count} negative")
    if pos_count < 50 or neg_count < 100:
        raise SystemExit("Not enough training windows — check espeak/ffmpeg")

    pos_feats = [x for x, y in samples if y >= 0.5]
    neg_feats = [x for x, y in samples if y < 0.5]
    n = min(len(pos_feats), len(neg_feats))
    pos_feats = random.sample(pos_feats, n)
    neg_feats = random.sample(neg_feats, n)

    X = np.stack(pos_feats + neg_feats)
    y = np.array([1.0] * n + [0.0] * n, dtype=np.float32)

    perm = np.random.permutation(len(y))
    X, y = X[perm], y[perm]

    split = int(0.85 * len(y))
    X_train, y_train = X[:split], y[:split]
    X_val, y_val = X[split:], y[split:]

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train[:, None]))
    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)

    model = WakeNet()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()

    best_val = 0.0
    best_state = None
    for epoch in range(80):
        model.train()
        for xb, yb in train_loader:
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            vp = model(torch.from_numpy(X_val)).numpy().squeeze()
            val_acc = ((vp >= 0.5) == (y_val >= 0.5)).mean()
        if val_acc >= best_val:
            best_val = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        print(f"epoch {epoch + 1}: val_acc={val_acc:.3f}")

    if best_state:
        model.load_state_dict(best_state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src_name in ("melspectrogram.onnx", "embedding_model.onnx"):
        src = model_dir / src_name
        dst = OUT_DIR / src_name
        if not dst.exists():
            dst.write_bytes(src.read_bytes())

    out_path = OUT_DIR / "hi_pal_v0.1.onnx"
    model.eval()
    dummy = torch.randn(1, N_FRAMES, EMBED_DIM)
    # Match openWakeWord export naming for FFI runtime compatibility.
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        opset_version=18,
        input_names=["x.1"],
        output_names=["output"],
        dynamo=False,
    )
    data_file = out_path.with_suffix(".onnx.data")
    if data_file.exists():
        data_file.unlink()
    print(f"Wrote {out_path} (val_acc={best_val:.3f})")


if __name__ == "__main__":
    main()

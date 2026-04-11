#!/usr/bin/env python3
"""
collect_dataset.py — Visual Inspection Dataset Collection Tool

Captures training images for MobileNetV2 binary classifier (PASS / FAIL).
Hold the gripper manually and present objects to the camera at different angles.

Usage:
    python3 collect_dataset.py

Dependencies:
    pip install opencv-python pyserial
"""

import cv2
import os
import re
import sys
import glob
import time
from pathlib import Path

# ─── Sample catalogue ─────────────────────────────────────────────────────────

SAMPLES = {
    1: {"id": "s01", "cls": "PASS", "defect": "none",         "ref": "P001_PASS_clean"},
    2: {"id": "s02", "cls": "FAIL", "defect": "scratch",      "ref": "F001_FAIL_scratch"},
    3: {"id": "s03", "cls": "FAIL", "defect": "sidehole",     "ref": "F002_FAIL_sidehole"},
    4: {"id": "s04", "cls": "FAIL", "defect": "chip",         "ref": "F003_FAIL_chip"},
    5: {"id": "s05", "cls": "FAIL", "defect": "blob",         "ref": "F004_FAIL_blob"},
    6: {"id": "s06", "cls": "FAIL", "defect": "short",        "ref": "F005_FAIL_short"},
    7: {"id": "s07", "cls": "FAIL", "defect": "multiscratch", "ref": "F006_FAIL_multiscratch"},
    8: {"id": "s08", "cls": "FAIL", "defect": "flatside",     "ref": "F007_FAIL_flatside"},
    9: {"id": "s09", "cls": "FAIL", "defect": "dent",         "ref": "F008_FAIL_dent"},
}

# ─── Poses ────────────────────────────────────────────────────────────────────

POSE_LIST = ["P1", "P2", "P3", "P4", "P5"]

POSE_HINTS = {
    "P1": "Hold upright, front face toward camera (0 deg)",
    "P2": "Hold upright, rotated 90 deg clockwise",
    "P3": "Hold upright, back face toward camera (180 deg)",
    "P4": "Tilt object 40 deg toward camera — show top face",
    "P5": "Tilt object 40 deg away from camera — show bottom face",
}

POSE_ANGLE = {
    "P1": "0 deg front",
    "P2": "90 deg rotated",
    "P3": "180 deg back",
    "P4": "+40 deg tilt toward cam",
    "P5": "-40 deg tilt away",
}

# ─── Lighting conditions ──────────────────────────────────────────────────────

CONDITIONS = {
    "A": ("condA", "Normal lab light"),
    "B": ("condB", "Extra side light"),
    "C": ("condC", "Dim light"),
}

# ─── Gripper serial commands ──────────────────────────────────────────────────

GRIPPER_OPEN  = b'{"T":101,"spd":100,"acc":10}\n'
GRIPPER_CLOSE = b'{"T":102,"spd":100,"acc":10,"pos":500}\n'

# ─── Font ─────────────────────────────────────────────────────────────────────

FONT       = cv2.FONT_HERSHEY_SIMPLEX
FONT_SMALL = 0.42
FONT_MED   = 0.52
FONT_BIG   = 0.62


# ══════════════════════════════════════════════════════════════════════════════
# Gripper helpers
# ══════════════════════════════════════════════════════════════════════════════

def detect_serial_port():
    """Return path of first detectable serial port, or None."""
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if ports:
            return ports[0].device
    except Exception:
        pass
    # Fallback: glob common paths
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*"):
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


def open_gripper(port, baud=115200):
    try:
        import serial
        ser = serial.Serial(port, baud, timeout=1)
        return ser
    except Exception:
        return None


def send_gripper(ser, cmd_bytes):
    if ser is None:
        return
    try:
        ser.write(cmd_bytes)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# File naming helpers
# ══════════════════════════════════════════════════════════════════════════════

def build_filename(cls, defect, sample_id, pose, condition, seq):
    return f"{cls}_{defect}_{sample_id}_{pose}_{condition}_{seq:03d}.jpg"


def get_starting_seq(raw_dir: Path, cls, defect, sample_id, pose, condition):
    """Scan raw_dir for existing images with this combo; return next SEQ."""
    pattern = str(raw_dir / f"{cls}_{defect}_{sample_id}_{pose}_{condition}_*.jpg")
    existing = glob.glob(pattern)
    if not existing:
        return 1
    nums = []
    for f in existing:
        m = re.search(r"_(\d{3})\.jpg$", f)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


def count_dataset(raw_dir: Path):
    """Return (pass_count, fail_count) of .jpg files directly in raw_dir."""
    # Count only flat files (ignore old subdirectory images)
    pass_count = len([f for f in raw_dir.glob("PASS_*.jpg") if f.is_file()])
    fail_count = len([f for f in raw_dir.glob("FAIL_*.jpg") if f.is_file()])
    return pass_count, fail_count


# ══════════════════════════════════════════════════════════════════════════════
# Overlay drawing
# ══════════════════════════════════════════════════════════════════════════════

def draw_overlay(frame, sample, cond_key, cond_label, pose_idx,
                 pose_counts, session_total, border_color=None):
    """Draw info overlay and optional border flash onto frame (in-place)."""
    h, w = frame.shape[:2]
    pose = POSE_LIST[pose_idx]
    s = sample

    # ── Build text lines ──────────────────────────────────────────────────────
    top_lines = [
        f"Sample: {s['id']} | {s['cls']} | {s['defect']}",
        f"Pose:   {pose}  ({POSE_ANGLE[pose]})",
        f"Light:  {cond_key}  — {cond_label}",
        f"Captured this pose: {pose_counts[pose]}",
        f"Total this session: {session_total}",
    ]
    bottom_hint = POSE_HINTS[pose]
    ctrl_hint   = "SPC=capture  N/B=pose  D=delete  O/C=gripper  I=info  Q=quit"

    # ── Measure sizes ─────────────────────────────────────────────────────────
    line_h = 22
    pad    = 8
    top_block_h = len(top_lines) * line_h + pad * 2

    widths = [cv2.getTextSize(l, FONT, FONT_MED, 1)[0][0] for l in top_lines]
    top_block_w = max(widths) + pad * 2

    (hint_w, hint_h), _ = cv2.getTextSize(bottom_hint, FONT, FONT_SMALL, 1)
    (ctrl_w, ctrl_h), _ = cv2.getTextSize(ctrl_hint,   FONT, FONT_SMALL, 1)

    # ── Draw semi-transparent backgrounds ────────────────────────────────────
    overlay = frame.copy()

    # Top-left info block
    cv2.rectangle(overlay,
                  (4, 4),
                  (4 + top_block_w, 4 + top_block_h),
                  (0, 0, 0), -1)

    # Bottom hint bar
    cv2.rectangle(overlay,
                  (4, h - hint_h - pad * 2),
                  (4 + hint_w + pad * 2, h - 4),
                  (0, 0, 0), -1)

    # Bottom-right controls bar
    cv2.rectangle(overlay,
                  (w - ctrl_w - pad * 2 - 4, h - ctrl_h - pad * 2),
                  (w - 4, h - 4),
                  (0, 0, 0), -1)

    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    # ── Draw text ─────────────────────────────────────────────────────────────
    y = 4 + pad + line_h - 4
    for line in top_lines:
        cv2.putText(frame, line, (4 + pad, y),
                    FONT, FONT_MED, (255, 255, 255), 1, cv2.LINE_AA)
        y += line_h

    cv2.putText(frame, bottom_hint,
                (4 + pad, h - pad - 4),
                FONT, FONT_SMALL, (180, 255, 180), 1, cv2.LINE_AA)

    cv2.putText(frame, ctrl_hint,
                (w - ctrl_w - pad - 4, h - pad - 4),
                FONT, FONT_SMALL, (180, 180, 180), 1, cv2.LINE_AA)

    # ── Border flash ──────────────────────────────────────────────────────────
    if border_color is not None:
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), border_color, 8)


# ══════════════════════════════════════════════════════════════════════════════
# Camera
# ══════════════════════════════════════════════════════════════════════════════

def find_camera_index():
    """
    Scan /sys/class/video4linux/ for device names, prefer UGREEN.
    Falls back to trying indices 0-7 in order.
    Returns the integer index to pass to VideoCapture.
    """
    import glob as _glob
    prefer_keywords = ("ugreen", "ultra hd", "4k")
    fallback_index  = None

    entries = sorted(_glob.glob("/sys/class/video4linux/video*/name"))
    for name_path in entries:
        try:
            name = open(name_path).read().strip().lower()
            idx  = int(os.path.basename(os.path.dirname(name_path)).replace("video", ""))
        except Exception:
            continue
        if any(kw in name for kw in prefer_keywords):
            print(f"Detected UGREEN camera at /dev/video{idx}  ({name})")
            return idx
        if fallback_index is None:
            fallback_index = idx   # first any-camera found

    return fallback_index if fallback_index is not None else 0


def open_camera():
    idx = find_camera_index()
    # Try preferred index first, then scan 0-7 as last resort
    for i in ([idx] + [x for x in range(8) if x != idx]):
        cap = cv2.VideoCapture(i, cv2.CAP_V4L2)
        if cap.isOpened():
            print(f"Camera opened on index {i}")
            return cap
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Session setup
# ══════════════════════════════════════════════════════════════════════════════

def prompt_session():
    print()
    print("═" * 55)
    print("  Visual Inspection — Dataset Collection")
    print("═" * 55)

    # ── Sample ────────────────────────────────────────────────────────────────
    print("\nSelect sample:")
    for k, v in SAMPLES.items():
        print(f"  [{k}] {v['id']} — {v['cls']:<4} / {v['defect']:<14}  ({v['ref']})")
    while True:
        raw = input("\nSample [1-9]: ").strip()
        if raw.isdigit() and int(raw) in SAMPLES:
            sample_key = int(raw)
            break
        print("  Invalid — enter a number from 1 to 9.")

    # ── Lighting ──────────────────────────────────────────────────────────────
    print("\nLighting condition:")
    for k, (cond_key, cond_label) in CONDITIONS.items():
        print(f"  [{k}] {cond_key} — {cond_label}")
    while True:
        raw = input("Condition [A/B/C]: ").strip().upper()
        if raw in CONDITIONS:
            cond_key, cond_label = CONDITIONS[raw]
            break
        print("  Invalid — enter A, B, or C.")

    # ── Output directory ──────────────────────────────────────────────────────
    default_out = "./dataset/raw"
    raw = input(f"\nOutput directory [{default_out}]: ").strip()
    raw_dir = Path(raw) if raw else Path(default_out)
    raw_dir.mkdir(parents=True, exist_ok=True)

    return sample_key, cond_key, cond_label, raw_dir


# ══════════════════════════════════════════════════════════════════════════════
# Main capture loop
# ══════════════════════════════════════════════════════════════════════════════

def run_session(sample_key, cond_key, cond_label, raw_dir):
    sample = SAMPLES[sample_key]

    # ── Gripper ───────────────────────────────────────────────────────────────
    ser = None
    try:
        import serial  # noqa: F401  (just test import)
        port = detect_serial_port()
        if port:
            ser = open_gripper(port)
            if ser and ser.isOpen():
                print(f"Gripper connected on {port}")
            else:
                ser = None
                print("No gripper detected — running without gripper control")
        else:
            print("No gripper detected — running without gripper control")
    except ImportError:
        print("pyserial not installed — running without gripper control")

    # ── Camera ────────────────────────────────────────────────────────────────
    cap = open_camera()
    if cap is None:
        print("ERROR: Could not open camera on index 0 or 1.")
        return

    # ── State ─────────────────────────────────────────────────────────────────
    pose_idx    = 0
    pose_counts = {p: 0 for p in POSE_LIST}

    # Pre-compute starting SEQ for every (pose) combination
    seq_counters = {
        pose: get_starting_seq(raw_dir, sample["cls"], sample["defect"],
                               sample["id"], pose, cond_key)
        for pose in POSE_LIST
    }

    session_files = []      # filenames saved this session (for undo)

    border_color = None
    border_until = 0.0

    # ── Window ────────────────────────────────────────────────────────────────
    win = f"Dataset Collector  |  {sample['id']}  {sample['cls']}/{sample['defect']}  {cond_key}"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 800, 600)

    print(f"\nSession ready: {sample['id']} | {sample['cls']} | "
          f"{sample['defect']} | {cond_key}")
    print("Controls:  SPACE/ENTER=capture  N=next pose  B=prev  D=delete  "
          "O=open gripper  C=close gripper  I=info  Q/ESC=quit")
    print("─" * 60)

    # ── Capture loop ──────────────────────────────────────────────────────────
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.03)
            continue

        # Resize for display while keeping aspect ratio within 800×600
        dh, dw = frame.shape[:2]
        scale  = min(800 / dw, 600 / dh, 1.0)
        disp   = cv2.resize(frame, (int(dw * scale), int(dh * scale)),
                            interpolation=cv2.INTER_LINEAR)

        now           = time.time()
        active_border = border_color if now < border_until else None

        draw_overlay(disp, sample, cond_key, cond_label, pose_idx,
                     pose_counts, len(session_files),
                     border_color=active_border)

        cv2.imshow(win, disp)
        key = cv2.waitKey(30) & 0xFF

        # ── SPACE / ENTER — capture ───────────────────────────────────────────
        if key in (ord(' '), 13):
            pose     = POSE_LIST[pose_idx]
            seq      = seq_counters[pose]
            filename = build_filename(sample["cls"], sample["defect"],
                                      sample["id"], pose, cond_key, seq)
            filepath = raw_dir / filename
            cv2.imwrite(str(filepath), frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
            seq_counters[pose] += 1
            pose_counts[pose]  += 1
            session_files.append(filename)
            print(f"  Saved [{pose}]: {filename}")
            border_color = (0, 255, 0)   # green
            border_until = time.time() + 0.5

        # ── N — next pose ─────────────────────────────────────────────────────
        elif key in (ord('n'), ord('N')):
            pose_idx     = (pose_idx + 1) % len(POSE_LIST)
            border_color = (0, 255, 255)   # yellow
            border_until = time.time() + 0.5
            print(f"  Pose → {POSE_LIST[pose_idx]}  "
                  f"({POSE_HINTS[POSE_LIST[pose_idx]]})")

        # ── B — previous pose ─────────────────────────────────────────────────
        elif key in (ord('b'), ord('B')):
            pose_idx     = (pose_idx - 1) % len(POSE_LIST)
            border_color = (0, 255, 255)   # yellow
            border_until = time.time() + 0.5
            print(f"  Pose → {POSE_LIST[pose_idx]}  "
                  f"({POSE_HINTS[POSE_LIST[pose_idx]]})")

        # ── D — delete last captured image ────────────────────────────────────
        elif key in (ord('d'), ord('D')):
            if not session_files:
                print("  Nothing to delete.")
            else:
                last = session_files[-1]
                confirm = input(f"  Delete {last}? [y/N]: ").strip().lower()
                if confirm == 'y':
                    filepath = raw_dir / last
                    if filepath.exists():
                        filepath.unlink()
                    # Parse pose from filename (index 3 after splitting on '_')
                    stem   = Path(last).stem          # strip .jpg
                    parts  = stem.split("_")
                    del_pose = parts[3] if len(parts) >= 4 else None
                    if del_pose and del_pose in pose_counts:
                        pose_counts[del_pose]  = max(0, pose_counts[del_pose] - 1)
                        seq_counters[del_pose] = max(1, seq_counters[del_pose] - 1)
                    session_files.pop()
                    print(f"  Deleted: {last}")
                else:
                    print("  Delete cancelled.")

        # ── O — open gripper ──────────────────────────────────────────────────
        elif key in (ord('o'), ord('O')):
            send_gripper(ser, GRIPPER_OPEN)
            print("  Gripper: OPEN")

        # ── C — close gripper ─────────────────────────────────────────────────
        elif key in (ord('c'), ord('C')):
            send_gripper(ser, GRIPPER_CLOSE)
            print("  Gripper: CLOSE")

        # ── I — image count summary ───────────────────────────────────────────
        elif key in (ord('i'), ord('I')):
            print("\n  Pose counts this session:")
            for p in POSE_LIST:
                print(f"    {p}: {pose_counts[p]}")
            print(f"  Session total: {len(session_files)}\n")

        # ── Q / ESC — quit ────────────────────────────────────────────────────
        elif key in (ord('q'), ord('Q'), 27):
            break

    # ── Teardown ──────────────────────────────────────────────────────────────
    cap.release()
    cv2.destroyAllWindows()
    if ser:
        try:
            ser.close()
        except Exception:
            pass

    # ── Session summary ───────────────────────────────────────────────────────
    pass_total, fail_total = count_dataset(raw_dir)

    print()
    print("═" * 43)
    print("  Session complete")
    print("═" * 43)
    print(f"  Sample:    {sample['id']} ({sample['cls']} / {sample['defect']})")
    print(f"  Condition: {cond_key}  ({cond_label})")
    print(f"  Captured this session: {len(session_files)} images")
    print()
    print("  Breakdown by pose:")
    for p in POSE_LIST:
        print(f"    {p}: {pose_counts[p]} images")
    print()
    print(f"  Dataset totals in raw/:")
    print(f"    PASS: {pass_total} images")
    print(f"    FAIL: {fail_total} images  (target: ~300 each)")
    print("═" * 43)
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    while True:
        sample_key, cond_key, cond_label, raw_dir = prompt_session()
        run_session(sample_key, cond_key, cond_label, raw_dir)

        ans = input("Start another session? [y/N]: ").strip().lower()
        if ans != 'y':
            break

    print("Done. All images saved to dataset/raw/")


if __name__ == "__main__":
    main()

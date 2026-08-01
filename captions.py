"""
captions.py

Ported from the working image_to_clip.py CLI script. Same caption text,
timing, styling, and zoom presets — just refactored into functions that
take an input path / output path per request instead of reading a global
CONFIG, since a web server handles many requests, not one run.
"""

import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CLIP_LENGTH = 6   # seconds
FPS = 30
TARGET_W = 1080   # fixed 9:16 output — TikTok/Reels size, no letterboxing
TARGET_H = 1920

FONT_PATH = str(Path(__file__).parent / "Poppins-Bold.ttf")

CAPTIONS = [
    {
        "text": "4 REMOTE JOBS",
        "start": 0,
        "y": "h*0.22",
        "max_width_frac": 0.6,
        "fontcolor": "white",
        "box": True,
        "boxcolor": "black@0.85",
        "box_pad_x_frac": 0.42,
        "box_pad_y_frac": 0.20,
        "box_corner_radius_frac": 0.28,
    },
    {
        "text": "Always Hiring + Good Pay",
        "start": 1.8,
        "y": "h*0.26",
        "max_width_frac": 0.9,
        "fontcolor": "black",
        "box": False,
        "bordercolor": "white",
        "border_frac": 0.16,
    },
    {
        "text": "List in the caption",
        "start": 3.3,  # 1.8 + 1.5
        "y": "h*0.75",
        "max_width_frac": 0.85,
        "fontcolor": "black",
        "box": False,
        "bordercolor": "white",
        "border_frac": 0.16,
    },
]

ZOOM_PRESETS = {
    "zoom_in_center": {
        "z": "min(zoom+{step},{max_zoom})",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
        "start_zoom": 1.0,
        "end_zoom": 1.4,
    },
    "zoom_out_center": {
        "z": "max({start_zoom}-{step}*on,{end_zoom})",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
        "start_zoom": 1.4,
        "end_zoom": 1.0,
    },
}


def escape_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")
    )


def escape_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:")


def estimate_fontsize(text, video_width, max_width_frac,
                       char_width_ratio=0.62, min_size=20, max_size_frac=0.16):
    target_width = video_width * max_width_frac
    size = target_width / (max(len(text), 1) * char_width_ratio)
    size = max(min_size, min(size, video_width * max_size_frac))
    return round(size)


def estimate_fontsize_with_padding(text, video_width, target_total_frac, pad_x_frac,
                                    char_width_ratio=0.62, min_size=20, max_size_frac=0.16):
    n = max(len(text), 1)
    denom = n * char_width_ratio + 2 * pad_x_frac
    size = (target_total_frac * video_width) / denom
    size = max(min_size, min(size, video_width * max_size_frac))
    return round(size)


def generate_rounded_box_png(text, fontsize, pad_x, pad_y, radius, opacity, out_path):
    font = ImageFont.truetype(FONT_PATH, fontsize)
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    box_w = int(text_w + 2 * pad_x)
    box_h = int(text_h + 2 * pad_y)
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    alpha = int(255 * opacity)
    draw.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=radius, fill=(0, 0, 0, alpha))
    img.save(out_path)
    return box_w, box_h


def build_drawtext_only(cap, video_width, output_label, input_label):
    text = escape_text(cap["text"])
    fontsize = estimate_fontsize(cap["text"], video_width, cap.get("max_width_frac", 0.85))
    parts = [
        f"text='{text}'",
        f"fontfile='{escape_path(FONT_PATH)}'",
        f"fontsize={fontsize}",
        f"fontcolor={cap.get('fontcolor', 'white')}",
        "x=(w-text_w)/2",
        f"y={cap.get('y', 'h*0.5')}",
        f"enable='gte(t,{cap['start']})'",
    ]
    if cap.get("border_frac"):
        borderw = max(1, round(fontsize * cap["border_frac"]))
        parts.append(f"borderw={borderw}")
        parts.append(f"bordercolor={cap.get('bordercolor', 'black')}")
    return f"{input_label}drawtext=" + ":".join(parts) + f"{output_label}"


def build_zoompan_expr(preset, total_frames):
    start_zoom = preset["start_zoom"]
    end_zoom = preset["end_zoom"]
    step = abs(end_zoom - start_zoom) / total_frames
    z = preset["z"].format(step=step, max_zoom=end_zoom, start_zoom=start_zoom, end_zoom=end_zoom)
    y = preset["y"].format(d=total_frames)
    x = preset["x"]
    return z, x, y


def render_clip(input_image: str, out_path: str, preset_name: str, work_dir: Path):
    """Render one captioned zoom clip from a still image. Raises RuntimeError
    with ffmpeg's stderr on failure."""
    preset = ZOOM_PRESETS[preset_name]
    orig_w, orig_h = Image.open(input_image).size

    # Fixed 9:16 output canvas — the crop-to-fill happens in the filter
    # chain below, so every photo (whatever its original aspect) fills the
    # frame edge-to-edge with no letterboxing.
    img_w, img_h = TARGET_W, TARGET_H

    total_frames = CLIP_LENGTH * FPS
    z, x, y = build_zoompan_expr(preset, total_frames)

    title_cap = CAPTIONS[0]
    other_caps = CAPTIONS[1:]
    title_fontsize = estimate_fontsize_with_padding(
        title_cap["text"], img_w,
        title_cap.get("max_width_frac", 0.6),
        title_cap.get("box_pad_x_frac", 0.42),
    )
    pad_x = round(title_fontsize * title_cap.get("box_pad_x_frac", 0.42))
    pad_y = round(title_fontsize * title_cap.get("box_pad_y_frac", 0.30))

    box_png_path = str(work_dir / "title_box.png")
    _, box_h = generate_rounded_box_png(
        title_cap["text"], title_fontsize, pad_x, pad_y, radius=1,
        opacity=0.85, out_path=box_png_path,
    )
    radius = round(box_h * title_cap.get("box_corner_radius_frac", 0.28))
    generate_rounded_box_png(
        title_cap["text"], title_fontsize, pad_x, pad_y, radius=radius,
        opacity=0.85, out_path=box_png_path,
    )

    title_y_frac = title_cap.get("y", "h*0.22").replace("h*", "")

    def title_drawtext(output_label, input_label):
        text = escape_text(title_cap["text"])
        parts = [
            f"text='{text}'",
            f"fontfile='{escape_path(FONT_PATH)}'",
            f"fontsize={title_fontsize}",
            f"fontcolor={title_cap.get('fontcolor', 'white')}",
            "x=(w-text_w)/2",
            f"y={title_cap.get('y', 'h*0.5')}",
            f"enable='gte(t,{title_cap['start']})'",
        ]
        return f"{input_label}drawtext=" + ":".join(parts) + f"{output_label}"

    steps = []
    upscale_w = int(img_w * 1.6)
    steps.append(
        f"[0:v]scale={img_w}:{img_h}:force_original_aspect_ratio=increase,"
        f"crop={img_w}:{img_h},"
        f"scale={upscale_w}:-2,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={total_frames}:s={img_w}x{img_h}:fps={FPS},"
        f"setsar=1[zoomed]"
    )
    box_y_expr = f"(H*{title_y_frac})-{pad_y}"
    steps.append(
        f"[zoomed][1:v]overlay=x=(W-w)/2:y={box_y_expr}:enable='gte(t,{title_cap['start']})'[boxed]"
    )
    all_caps_after_title = [title_cap] + other_caps
    prev_label = "[boxed]"
    for i, cap in enumerate(all_caps_after_title):
        out_label = f"[t{i}]" if i < len(all_caps_after_title) - 1 else "[vout]"
        if i == 0:
            filt = title_drawtext(out_label, prev_label)
        else:
            filt = build_drawtext_only(cap, img_w, out_label, prev_label)
        steps.append(filt)
        prev_label = out_label

    filter_str = ";".join(steps)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", input_image,
        "-loop", "1", "-i", box_png_path,
        "-filter_complex", filter_str,
        "-map", "[vout]",
        "-an",
        "-t", str(CLIP_LENGTH),
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-movflags", "+faststart",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])

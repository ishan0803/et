"""Video composer engine — ET Layout implementation using fast ffmpeg pipelines.

Pre-composites the complex ET UI (logo, side text panel, news ticker) with a 
transparent hole for the media. Uses ffmpeg to zoompan the media layer 
underneath the UI, and xfade between scenes.
"""

import os
import subprocess
import logging
from PIL import Image, ImageDraw, ImageFont
import datetime
import yfinance as yf

from app.config import (
    WIDTH, HEIGHT, FPS, FONT_BOLD, FONT_EXTRABOLD, FONT_SEMIBOLD
)

from app.models import Script, VisualPlan, VoiceResult, SceneVisual, MotionType
from app.utils.helpers import job_dir, job_output_dir, get_font_path

logger = logging.getLogger(__name__)

# Constants for the ET UI Layout
MEDIA_X = 100
MEDIA_Y = 160
MEDIA_W = 1040
MEDIA_H = 700
RENDER_FPS = 24

_ticker_cache = None

def _get_live_ticker_data():
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache
        
    data = {"SENSEX": (0.0, 0.0), "NIFTY": (0.0, 0.0)}
    try:
        df = yf.download("^BSESN ^NSEI", period="5d", progress=False)['Close']
        if not df.empty and '^BSESN' in df.columns:
            bsesn_closes = df['^BSESN'].dropna().values
            nsei_closes = df['^NSEI'].dropna().values
            
            s_val = float(bsesn_closes[-1]) if len(bsesn_closes) > 0 else 0
            s_prev = float(bsesn_closes[-2]) if len(bsesn_closes) > 1 else s_val
            s_pct = ((s_val - s_prev) / s_prev) * 100 if s_prev else 0
            
            n_val = float(nsei_closes[-1]) if len(nsei_closes) > 0 else 0
            n_prev = float(nsei_closes[-2]) if len(nsei_closes) > 1 else n_val
            n_pct = ((n_val - n_prev) / n_prev) * 100 if n_prev else 0
            
            data["SENSEX"] = (s_val, s_pct)
            data["NIFTY"] = (n_val, n_pct)
    except Exception as e:
        logger.warning(f"yfinance failed: {e}")
        
    _ticker_cache = data
    return data


def compose_video(
    script: Script,
    visual_plan: VisualPlan,
    voice_result: VoiceResult,
    scene_images: dict[int, str],
    chart_images: dict[int, str],
    job_id: str,
) -> str:
    work_dir = job_dir(job_id)
    output_dir = job_output_dir(job_id)
    output_path = os.path.join(output_dir, "final.mp4")
    scenes_dir = os.path.join(work_dir, "composited_scenes")
    os.makedirs(scenes_dir, exist_ok=True)

    segment_timings = _calculate_segment_timings(voice_result)
    scene_files = []  # (media_path, ui_path, duration, motion)

    cta_seg_id = script.segments[-1].segment_id
    filtered_scenes = []
    for scene in visual_plan.scenes:
        if len(scene.segment_ids) == 1 and scene.segment_ids[0] == cta_seg_id:
            logger.info(f"Omitting scene {scene.scene_id} as it is mapped exclusively to the CTA. Using end_sq.mp4 instead.")
            continue
        filtered_scenes.append(scene)

    for scene in filtered_scenes:
        duration = _get_scene_duration(scene, segment_timings)
        if duration <= 0:
            duration = max(scene.duration, 4.0)

        if scene.scene_id in chart_images:
            img_path = chart_images[scene.scene_id]
        elif scene.scene_id in scene_images:
            img_path = scene_images[scene.scene_id]
        else:
            img_path = next(iter(scene_images.values()), None)
            if not img_path:
                continue

        # Get the script segment text for the footer
        seg_text = script.segments[0].text
        if scene.segment_ids:
            seg_texts = [s.text for s in script.segments if s.segment_id in scene.segment_ids]
            seg_text = " ".join(seg_texts)

        ui_path = os.path.join(scenes_dir, f"ui_{scene.scene_id}.png")
        _composite_ui_image(scene, seg_text, script.title, ui_path)
        
        scene_files.append((img_path, ui_path, duration, scene.motion_type))

    if not scene_files:
        raise ValueError("No scenes to compose")

    main_mp4 = os.path.join(work_dir, "main.mp4")
    _build_video_ffmpeg(scene_files, voice_result.main_audio_path, voice_result.main_duration, main_mp4)
    
    _concat_final_broadcast(main_mp4, voice_result.cta_audio_path, output_path, work_dir)
    return output_path


def _composite_ui_image(scene: SceneVisual, script_text: str, title: str, output_path: str):
    """Draw the ET graphical interface with a transparent hole for media."""
    ticker_data = _get_live_ticker_data()
    script_text = script_text.replace("*", "").replace("**", "")

    ui = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui)

    # Base Gradient Background (light gray map aesthetic)
    for y in range(HEIGHT):
        r = int(243 - (243 - 209) * (y / HEIGHT))
        g = int(244 - (244 - 213) * (y / HEIGHT))
        b = int(246 - (246 - 219) * (y / HEIGHT))
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b, 255))
    
    # Cut Transparent Media Window
    mask = Image.new("L", (WIDTH, HEIGHT), 255)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle([MEDIA_X, MEDIA_Y, MEDIA_X + MEDIA_W, MEDIA_Y + MEDIA_H], fill=0)
    ui.putalpha(mask)
    draw = ImageDraw.Draw(ui)

    # Media Border and Subtle Dark Shadow Line
    draw.rectangle([MEDIA_X-5, MEDIA_Y-5, MEDIA_X + MEDIA_W + 5, MEDIA_Y + MEDIA_H + 5], 
                   outline=(255,255,255,255), width=5)
    
    # Palette
    et_red = (185, 0, 0, 255)
    black = (0, 0, 0, 255)
    white = (255, 255, 255, 255)

    # Fonts
    try:
        font_logo_et = ImageFont.truetype(get_font_path(FONT_BOLD), 40)
        font_logo_text = ImageFont.truetype(get_font_path(FONT_SEMIBOLD), 38)
        font_box_header = ImageFont.truetype(get_font_path(FONT_EXTRABOLD), 48)
        font_headline = ImageFont.truetype(get_font_path(FONT_EXTRABOLD), 52)
        font_bullet = ImageFont.truetype(get_font_path("Montserrat-Medium"), 32)
        font_script = ImageFont.truetype(get_font_path("Montserrat-Regular"), 26)
        font_ticker = ImageFont.truetype(get_font_path(FONT_SEMIBOLD), 32)
    except Exception:
        font_logo_et = ImageFont.load_default()
        font_logo_text = ImageFont.load_default()
        font_box_header = ImageFont.load_default()
        font_headline = ImageFont.load_default()
        font_bullet = ImageFont.load_default()
        font_script = ImageFont.load_default()
        font_ticker = ImageFont.load_default()

    # ET Logo
    draw.rectangle([100, 50, 160, 110], fill=et_red)
    draw.text((106, 56), "ET", font=font_logo_et, fill=white)
    draw.text((180, 58), "THE ECONOMIC TIMES", font=font_logo_text, fill=(30, 30, 30, 255))

    # Right Text Panel
    px1, py1, px2, py2 = 1190, 160, 1850, 860
    draw.rectangle([px1+10, py1+10, px2+10, py2+10], fill=(0,0,0,30))  # Shadow
    draw.rectangle([px1, py1, px2, py2], fill=white)
    
    # Panel Header
    draw.rectangle([px1, py1, px2, py1+80], fill=et_red)
    draw.text((px1+30, py1+15), "HEADLINE", font=font_box_header, fill=white)

    # Headline
    headline = getattr(scene, 'headline', "LATEST UPDATE").replace("*", "").replace("**", "")
    h_lines = _wrap_text(headline.upper(), font_headline, px2 - px1 - 60)
    cursor_y = py1 + 100
    for line in h_lines[:2]:
        draw.text((px1+30, cursor_y), line, font=font_headline, fill=black)
        cursor_y += 60
    
    cursor_y += 20

    # Bullets (Strict max of 3, strip asterisks, prevent overflow)
    bullets = getattr(scene, 'bullet_points', ["Details emerging", "Standby for updates"])
    bullets = [b.replace("*", "").replace("**", "") for b in bullets]
    for bullet in bullets[:3]:
        draw.rectangle([px1+30, cursor_y+12, px1+42, cursor_y+24], fill=et_red)
        b_lines = _wrap_text(bullet, font_bullet, px2 - px1 - 90)
        for line in b_lines[:2]:
            draw.text((px1+60, cursor_y), line, font=font_bullet, fill=(40,40,40,255))
            cursor_y += 40
        cursor_y += 15
        if cursor_y > 620:
            break

    # Footer Separator
    sep_y = 660
    draw.line([(px1+30, sep_y), (px2-30, sep_y)], fill=(200,200,200,255), width=2)
    draw.text((px1+30, sep_y+20), "Financial insights & market data.", font=font_bullet, fill=(60,60,60,255))
    
    # Script segment text
    s_lines = _wrap_text(script_text, font_script, px2 - px1 - 60)
    py = sep_y + 65
    for line in s_lines[:4]:
        draw.text((px1+30, py), line, font=font_script, fill=(100,100,100,255))
        py += 32

    # Ticker Bottom Bar
    ty = 960
    draw.rectangle([0, ty-5, WIDTH, ty], fill=et_red) # Top trim
    draw.rectangle([0, ty, WIDTH, HEIGHT], fill=(26, 26, 26, 255))
    
    # Ticker Clock/Info Left Side
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%d %b %Y").upper()

    draw.rectangle([0, ty, 220, HEIGHT], fill=(230,230,230,255))
    draw.text((60, ty+15), time_str, font=font_ticker, fill=black)
    draw.text((45, ty+60), date_str, font=font_script, fill=(80,80,80,255))
    
    draw.rectangle([220, ty, 620, HEIGHT], fill=(210,210,210,255))
    s_val, s_pct = ticker_data["SENSEX"]
    n_val, n_pct = ticker_data["NIFTY"]
    
    s_color = (0, 150, 0, 255) if s_pct >= 0 else et_red
    n_color = (0, 150, 0, 255) if n_pct >= 0 else et_red
    
    s_str = f"{s_val:,.0f} (+{s_pct:.2f}%)" if s_pct >= 0 else f"{s_val:,.0f} ({s_pct:.2f}%)"
    n_str = f"{n_val:,.0f} (+{n_pct:.2f}%)" if n_pct >= 0 else f"{n_val:,.0f} ({n_pct:.2f}%)"

    draw.text((250, ty+18), "SENSEX", font=font_script, fill=(80,80,80,255))
    draw.text((400, ty+18), s_str, font=font_script, fill=s_color)
    
    draw.text((250, ty+60), "NIFTY", font=font_script, fill=(80,80,80,255))
    draw.text((400, ty+60), n_str, font=font_script, fill=n_color)

    # Scrolling Headline (static for now)
    title_clean = title.upper().replace("*", "")
    draw.text((650, ty + 35), f"BREAKING: {title_clean}", font=font_ticker, fill=white)

    ui.save(output_path, "PNG")


def _build_video_ffmpeg(scene_files, audio_path, audio_dur, output_path):
    # Adjust to audio duration
    total_dur = sum(d for _, _, d, _ in scene_files)
    if abs(total_dur - audio_dur) > 2:
        ratio = audio_dur / total_dur
        scene_files = [(m, u, d * ratio, mp) for m, u, d, mp in scene_files]

    xf_dur = 0.4
    inputs = []
    filters = []

    # One scene case
    if len(scene_files) == 1:
        img_path, ui_path, duration, motion = scene_files[0]
        zp = _zoompan_filter(motion, duration)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-loop", "1", "-i", ui_path,
            "-i", audio_path,
            "-filter_complex",
            f"[0:v]{zp}[media];[media]pad={WIDTH}:{HEIGHT}:{MEDIA_X}:{MEDIA_Y}:color=black@0[padded];"
            f"[padded][1:v]overlay=0:0[v]",
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-t", str(audio_dur), output_path
        ]
        subprocess.run(cmd, check=True)
        return

    # Multi-scene case
    for i, (img_path, ui_path, duration, motion) in enumerate(scene_files):
        vid_idx = i * 2
        ui_idx = i * 2 + 1
        inputs.extend(["-loop", "1", "-t", str(duration + 1), "-i", img_path])
        inputs.extend(["-loop", "1", "-t", str(duration + 1), "-i", ui_path])
        
        zp = _zoompan_filter(motion, duration)
        # Media zoompan -> Pad to full size -> Overlay UI -> output stream [vN]
        f = (
            f"[{vid_idx}:v]{zp}[m{i}];"
            f"[m{i}]pad={WIDTH}:{HEIGHT}:{MEDIA_X}:{MEDIA_Y}:color=black@0[pm{i}];"
            f"[pm{i}][{ui_idx}:v]overlay=0:0[v{i}]"
        )
        filters.append(f)

    # Chain xfade
    if len(scene_files) == 2:
        offset = scene_files[0][2] - xf_dur
        filters.append(f"[v0][v1]xfade=transition=fade:duration={xf_dur}:offset={max(0, offset)}[vout]")
    else:
        cum_offset = 0
        prev = "v0"
        for i in range(1, len(scene_files)):
            cum_offset += scene_files[i-1][2] - xf_dur
            out = "vout" if i == len(scene_files) - 1 else f"xf{i}"
            filters.append(
                f"[{prev}][v{i}]xfade=transition=fade:duration={xf_dur}:offset={max(0, cum_offset)}[{out}]"
            )
            prev = out

    filter_complex = ";".join(filters)
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", f"{len(scene_files) * 2}:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-t", str(audio_dur), output_path
    ]
    subprocess.run(cmd, check=True)

def _concat_final_broadcast(main_video_path, cta_audio_path, output_path, work_dir):
    """Combines Opening_sq, Main Content, and end_sq with CTA VO using exact FFmpeg conforming."""
    intro_path = "/app/media/Opening_sq.mp4"
    outro_path = "/app/media/end_sq.mp4"
    
    # 1. Overlay CTA Audio onto End Sequence
    # We create a conformed synced_outro.mp4
    synced_outro = os.path.join(work_dir, "synced_outro.mp4")
    if os.path.exists(outro_path):
        # We loop the outro video or just let it play over the CTA audio. 
        # -stream_loop -1 loops the video. We cut it at the length of the audio or video.
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", outro_path,
            "-i", cta_audio_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-shortest", synced_outro
        ]
        subprocess.run(cmd, check=True)
    
    # 2. Concat Intro + Main + Synced Outro
    # Using conform filters (scale, fps, setsar) and aresample to ensure concat doesn't crash on format mismatches
    concat_list = []
    if os.path.exists(intro_path):
        concat_list.append(intro_path)
    concat_list.append(main_video_path)
    if os.path.exists(synced_outro):
        concat_list.append(synced_outro)
        
    inputs = []
    filters = []
    for i, path in enumerate(concat_list):
        inputs.extend(["-i", path])
        # Conform each input to exactly 1080x1920, 24fps, and 44100Hz stereo
        f = (
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1,fps={RENDER_FPS},format=yuv420p[v{i}];"
            f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]"
        )
        filters.append(f)
        
    concat_filter = "".join(f"[v{i}][a{i}]" for i in range(len(concat_list)))
    concat_filter += f"concat=n={len(concat_list)}:v=1:a=1[vout][aout]"
    
    filter_complex = ";".join(filters) + ";" + concat_filter
    
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]
    subprocess.run(cmd, check=True)


def _zoompan_filter(motion: MotionType, duration: float) -> str:
    frames = int(duration * RENDER_FPS)
    s = f"{MEDIA_W}x{MEDIA_H}"
    if motion in (MotionType.ZOOM_IN, MotionType.KEN_BURNS):
        return f"zoompan=z='1+0.05*on/({frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={s}:fps={RENDER_FPS}"
    if motion == MotionType.ZOOM_OUT:
        return f"zoompan=z='1.05-0.05*on/({frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={s}:fps={RENDER_FPS}"
    return f"zoompan=z='1+0.03*on/({frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={s}:fps={RENDER_FPS}"


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        if font.getbbox(test)[2] > max_width and current:
            lines.append(current)
            current = w
        else:
            current = test
    if current: lines.append(current)
    return lines

def _calculate_segment_timings(voice_result):
    t = {}
    c = 0.2
    for s in voice_result.segments:
        t[s.segment_id] = (c, c + s.duration)
        c += s.duration + 0.5
    return t

def _get_scene_duration(scene, timings):
    if not scene.segment_ids: return scene.duration
    s = [timings[x][0] for x in scene.segment_ids if x in timings]
    e = [timings[x][1] for x in scene.segment_ids if x in timings]
    if s and e: return max(e) - min(s) + 0.5
    return scene.duration

from flask import Flask, render_template, request, jsonify, send_from_directory, session, send_file
import os
import subprocess
import json
from moviepy.editor import VideoFileClip, concatenate_videoclips, vfx, CompositeVideoClip, TextClip
from moviepy.config import change_settings
# ImageMagick のパスを設定
IMAGEMAGICK_BINARY = os.popen("which convert").read().strip()
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})

# 既存のインポートと他のコード
from flask import Flask, render_template, request, jsonify, send_from_directory, session, send_file
# ... 他のインポートと設定 ...
from datetime import datetime, timezone
from PIL import Image
import PIL
from mutagen.mp4 import MP4
from cache_manager import cache
from flask import Flask, jsonify, request, session, send_from_directory
import uuid
from werkzeug.utils import secure_filename
from celery import Celery
from moviepy.video.fx.all import resize
import numpy as np
from flask import jsonify
import traceback
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="moviepy")
import re
from flask import abort
import mimetypes
import logging
from flask import Flask, render_template, request, jsonify, send_file, abort, Response
import time
from proglog import ProgressBarLogger
from tqdm import tqdm
import json
import subprocess

import json
import subprocess
from werkzeug.utils import secure_filename

import shutil
import threading
import cv2

import glob
from datetime import datetime, timedelta

import pytz

import logging
logging.basicConfig(level=logging.DEBUG)

def adaptive_audio_processing(input_path, output_path, target_lufs=-14, intensity='medium', preserve_quiet=True):
    # 入力音声の分析
    analyze_command = [
        "ffmpeg", "-i", input_path,
        "-af", "loudnorm=print_format=json", "-f", "null", "-"
    ]
    analysis = subprocess.run(analyze_command, capture_output=True, text=True)
    analysis_data = json.loads(analysis.stderr.split("Parsed_loudnorm")[1])

    # 分析結果に基づいてパラメータを調整
    input_i = float(analysis_data['input_i'])
    input_lra = float(analysis_data['input_lra'])
    input_tp = float(analysis_data['input_tp'])

    # インテンシティと静かな部分の保持設定に基づいてパラメータを設定
    if intensity == 'low':
        gate_threshold = 0.005 if preserve_quiet else 0.01
        compand_points = "-90/-90|-70/-70|-20/-20|0/-10"
        lra_target = 20
    elif intensity == 'medium':
        gate_threshold = 0.01 if preserve_quiet else 0.03
        compand_points = "-90/-90|-70/-65|-20/-15|0/-10"
        lra_target = 15 if preserve_quiet else 11
    else:  # high
        gate_threshold = 0.02 if preserve_quiet else 0.05
        compand_points = "-90/-90|-70/-60|-20/-15|0/-9"
        lra_target = 11 if preserve_quiet else 7

    # 音声フィルターの構築
    audio_filter = (
        f"agate=threshold={gate_threshold},"
        f"compand=attacks=0:decays=0.1:points={compand_points}:soft-knee=0.01:gain=1,"
        f"loudnorm=I={target_lufs}:TP=-1:LRA={lra_target}:"
        f"measured_I={input_i}:measured_LRA={input_lra}:measured_TP={input_tp}:"
        f"measured_thresh=-10:offset=0.5:linear=true:print_format=summary"
    )

    # 音声処理の実行
    ffmpeg_command = [
        "ffmpeg", "-i", input_path,
        "-af", audio_filter,
        "-ar", "44100", "-c:v", "copy", "-c:a", "aac",
        output_path  # ここにoutput_pathを追加
    ]
    
    subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)

app = Flask(__name__)

# Flaskの設定
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'  # Redisを使用する場合
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'


celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

@celery.task(bind=True)
def process_audio_task(self, video, settings):
    try:
        apply_audio_processing(secure_filename(video), settings)
        return {'status': 'success', 'video': video}
    except Exception as e:
        return {'status': 'error', 'video': video, 'error': str(e)}


class MyBarLogger(ProgressBarLogger):
    def __init__(self):
        super().__init__()
        self.bar = None

    def bars_callback(self, bar, attr, value, old_value=None):
        if not self.bar:
            self.bar = tqdm(total=100, desc="Processing", unit="%")
        percentage = (value / self.bars[bar]['total']) * 100
        self.bar.n = percentage
        self.bar.refresh()

    def callback(self, **changes):
        # コンソールの出力をクリアするには、この行をアンコメントします
        # os.system('cls' if os.name == 'nt' else 'clear')
        super().callback(**changes)

    def finish(self):
        if self.bar:
            self.bar.close()

# PILのリサイズ方法を明示的に設定
if hasattr(Image, 'Resampling'):  # PIL 9.0.0以降
    RESIZE_METHOD = Image.Resampling.LANCZOS
elif hasattr(Image, 'LANCZOS'):  # PIL 7.0.0以降
    RESIZE_METHOD = Image.LANCZOS
else:  # 古いバージョン
    RESIZE_METHOD = Image.ANTIALIAS

def handle_error(error, status_code=400):
    app.logger.error(f"Error: {str(error)}\n{traceback.format_exc()}")
    return jsonify({
        "error": str(error),
        "status_code": status_code,
        "traceback": traceback.format_exc()
    }), status_code

def custom_resize(clip, newsize):
    def resize_frame(frame):
        return np.array(Image.fromarray(frame).resize(newsize, Image.LANCZOS))
    return clip.fl_image(resize_frame)

def get_video_orientation(clip):
    return 'horizontal' if clip.w >= clip.h else 'vertical'

def resize_clip(clip, target_height):
    if get_video_orientation(clip) == 'horizontal':
        return clip.resize(height=target_height)
    else:
        scale_factor = target_height / clip.w
        new_height = int(clip.h * scale_factor)
        new_width = target_height

        def resize_frame(frame):
            img = Image.fromarray(frame)
            resized_img = img.resize((new_width, new_height), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
            return np.array(resized_img)

        resized_clip = clip.fl_image(resize_frame)
        return resize_with_padding(resized_clip, target_height, target_height)

def resize_with_padding(clip, target_w, target_h):
    w, h = clip.w, clip.h
    if h > w:
        new_w = int(w * target_h / h)
        new_h = target_h
    else:
        new_w = target_w
        new_h = int(h * target_w / w)

    def resize_and_pad_frame(frame):
        img = Image.fromarray(frame)
        resized_img = img.resize((new_w, new_h), Image.LANCZOS)
        padded_img = Image.new('RGB', (target_w, target_h), (0, 0, 0))
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        padded_img.paste(resized_img, (paste_x, paste_y))
        return np.array(padded_img)

    return clip.fl_image(resize_and_pad_frame)

def generate_thumbnail(video_path, thumbnail_path):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(thumbnail_path, frame)
    cap.release()

def generate_thumbnail(video_path, thumbnail_path, size=(320, 180)):
    try:
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        if ret:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            pil_image.thumbnail(size, Image.LANCZOS)
            pil_image.save(thumbnail_path, "JPEG")
        else:
            raise Exception("Failed to read video frame")
        cap.release()
    except Exception as e:
        print(f"Error generating thumbnail for {video_path}: {str(e)}")
        # エラーが発生した場合、黒い画像をデフォルトのサムネイルとして生成
        black_image = Image.new('RGB', size, color='black')
        black_image.save(thumbnail_path, "JPEG")


app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # セッション用のシークレットキーを設定

SAVE_FOLDER = 'saved_states'
if not os.path.exists(SAVE_FOLDER):
    os.makedirs(SAVE_FOLDER)


UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
OUTPUT_FOLDER = 'output'
TEMP_FOLDER = 'temp'
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['TEMP_FOLDER'] = TEMP_FOLDER

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# PILのリサイズ方法を明示的に設定
if hasattr(PIL.Image, 'Resampling'):  # PIL 9.0.0以降
    RESIZE_METHOD = PIL.Image.Resampling.LANCZOS
elif hasattr(PIL.Image, 'LANCZOS'):  # PIL 7.0.0以降
    RESIZE_METHOD = PIL.Image.LANCZOS
else:  # 古いバージョン
    RESIZE_METHOD = PIL.Image.ANTIALIAS

# アプリケーションの設定部分に以下を追加
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}  # 許可する動画ファイルの拡張子

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMP_FOLDER]:
    os.makedirs(folder, exist_ok=True)

def get_imagemagick_path():
    try:
        result = subprocess.run(['which', 'magick'], capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

imagemagick_path = get_imagemagick_path()
print(f"ImageMagick path: {imagemagick_path}")

os.environ['PATH'] = f"{imagemagick_path}:{os.environ['PATH']}"
change_settings({"IMAGEMAGICK_BINARY": imagemagick_path})

def run_ffmpeg_command(command):
    try:
        result = subprocess.run(command, check=True, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)
        return result.stderr
    except subprocess.CalledProcessError as e:
        print(f"Error executing ffmpeg command: {e}")
        print(f"FFmpeg stderr: {e.stderr}")
        print(f"FFmpeg stdout: {e.stdout}")
        return None

def get_valid_videos():
    if 'videos' not in session:
        session['videos'] = []
    
    valid_videos = []
    for video in session['videos']:
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], video)):
            valid_videos.append(video)
    
    session['videos'] = valid_videos
    session.modified = True
    return valid_videos

def handle_error(error_message, status_code=400):
    return jsonify({"error": error_message}), status_code

def process_video_in_chunks(input_file, output_file, chunk_size=10 * 1024 * 1024):  # 10MB chunks
    with open(input_file, 'rb') as infile, open(output_file, 'wb') as outfile:
        while True:
            chunk = infile.read(chunk_size)
            if not chunk:
                break
            # ここでchunkに対して必要な処理を行う
            processed_chunk = some_processing_function(chunk)
            outfile.write(processed_chunk)


@app.route('/start_processing', methods=['POST'])
def start_processing():
    data = request.json
    thread = threading.Thread(target=process_video, args=(data['input_file'], data['output_file']))
    thread.start()
    return jsonify({'message': 'Processing started'}), 202

@app.route('/add_text_overlay', methods=['POST'])
def add_text_overlay():
    try:
        app.logger.info("Received add_text_overlay request")
        data = request.json
        app.logger.info(f"Received data: {data}")

        video_filename = data.get('video_filename')
        overlay_text = data.get('text')
        position = data.get('position')
        color = data.get('color')
        font_size = int(data.get('font_size'))
        duration = data.get('duration')
        padding = int(data.get('padding', 10))

        if not video_filename:
            app.logger.error("Video filename is empty")
            return jsonify({'success': False, 'error': 'Video filename is empty'}), 400

        if not overlay_text:
            app.logger.error("Overlay text is empty")
            return jsonify({'success': False, 'error': 'Overlay text is empty'}), 400

        app.logger.info(f"Video filename: {video_filename}")

        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        app.logger.info(f"Input path: {input_path}")

        if not os.path.isfile(input_path):
            app.logger.error(f"File not found: {input_path}")
            return jsonify({'success': False, 'error': f"Input file not found: {input_path}"}), 404

        video = VideoFileClip(input_path)
        text_clip = TextClip(overlay_text, fontsize=font_size, color=color, font='Arial', stroke_color='black', stroke_width=1)
        
        padded_clip = text_clip.on_color(size=(text_clip.w + padding * 2, text_clip.h + padding * 2),
                                         color=(0,0,0,128), pos=(padding, padding))
        
        # 位置の設定（パディングを考慮）
        position_func = lambda w, h: ((w - padded_clip.w) // 2, (h - padded_clip.h) // 2)
        if position == 'top-left':
            position_func = lambda w, h: (padding, padding)
        elif position == 'top-right':
            position_func = lambda w, h: (w - padded_clip.w - padding, padding)
        elif position == 'bottom-left':
            position_func = lambda w, h: (padding, h - padded_clip.h - padding)
        elif position == 'bottom-right':
            position_func = lambda w, h: (w - padded_clip.w - padding, h - padded_clip.h - padding)
        
        text_position = position_func(video.w, video.h)
        padded_clip = padded_clip.set_position(text_position)

        # 動画の長さに合わせてテキストの表示時間を設定
        if duration == 'full':
            padded_clip = padded_clip.set_duration(video.duration)
        else:
            try:
                padded_clip = padded_clip.set_duration(float(duration))
            except ValueError:
                app.logger.warning(f"Invalid duration value: {duration}. Using full video duration.")
                padded_clip = padded_clip.set_duration(video.duration)

        final_clip = CompositeVideoClip([video, padded_clip])
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"overlay_{video_filename}")
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

        
        # ファイルが既に存在する場合は削除
        if os.path.exists(output_path):
            os.remove(output_path)
        
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")

        video.close()
        final_clip.close()

        return jsonify({'success': True, 'output_file': f"overlay_{video_filename}"})
    except Exception as e:
        app.logger.error(f"Error in add_text_overlay: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        app.logger.debug('Upload request received')
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400
        
        files = request.files.getlist('file')
        uploaded_files = []

        for file in files:
            if file.filename == '':
                continue
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # チャンクでファイルを保存
                with open(file_path, 'wb') as f:
                    while True:
                        chunk = file.stream.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                
                # サムネイル生成
                thumbnail_filename = f"{os.path.splitext(filename)[0]}_thumb.jpg"
                thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_filename)
                generate_thumbnail(file_path, thumbnail_path, size=(320, 180))

                # ビデオ情報を生成
                clip = VideoFileClip(file_path)
                video_info = {
                    'filename': filename,
                    'duration': clip.duration,
                    'size': os.path.getsize(file_path) / (1024 * 1024),  # Convert to MB
                    'resolution': f"{clip.w}x{clip.h}",
                    'creation_time': os.path.getctime(file_path),
                    'upload_time': time.time()
                }
                clip.close()
                
                # セッションにファイル名を追加
                if 'videos' not in session:
                    session['videos'] = []
                session['videos'].append(filename)
                session.modified = True
                
                uploaded_files.append({
                    'success': True,
                    'filename': filename,
                    'thumbnail': thumbnail_filename,
                    'video_info': video_info
                })

        return jsonify(uploaded_files), 200
    except Exception as e:
        app.logger.error('Error in upload_file: %s', str(e), exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    thumbnail_filename = f"{os.path.splitext(filename)[0]}_thumb.jpg"
    return send_from_directory(app.config['UPLOAD_FOLDER'], thumbnail_filename)

@app.route('/get_videos')
def get_videos():
    videos = get_valid_videos()
    app.logger.info(f"Returning videos: {videos}")
    return jsonify({'videos': videos})

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}")
    return handle_error("An unexpected error occurred. Please try again later.", 500)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(file_path):
        abort(404, description="File not found")

    file_size = os.path.getsize(file_path)
    
    range_header = request.headers.get('Range', None)
    if range_header:
        byte1, byte2 = 0, None
        match = re.search(r'(\d+)-(\d*)', range_header)
        if match:
            groups = match.groups()

            if groups[0]: byte1 = int(groups[0])
            if groups[1]: byte2 = int(groups[1])

        if byte2 is None or byte2 >= file_size:
            byte2 = file_size - 1

        if byte1 < 0 or byte1 >= file_size:
            return Response("Invalid range", status=416)

        length = byte2 - byte1 + 1
        
        resp = Response(
            get_chunk(file_path, byte1, length),
            206,
            mimetype=mimetypes.guess_type(file_path)[0],
            direct_passthrough=True
        )
        resp.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
        resp.headers.add('Accept-Ranges', 'bytes')
        resp.headers.add('Content-Length', str(length))
        return resp

    return send_file(file_path)

def get_chunk(filename, start, length):
    with open(filename, 'rb') as f:
        f.seek(start)
        chunk = f.read(length)
    return chunk

def generate_bytes(file_path, start, end):
    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining:
            chunk_size = min(4096, remaining)
            data = f.read(chunk_size)
            if not data:
                break
            yield data
            remaining -= len(data)


@app.route('/save_work_state', methods=['POST'])
def save_work_state():
    data = request.json
    state_name = data.get('name', datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    state = data.get('state', {})
    file_path = os.path.join(SAVE_FOLDER, f"{state_name}.json")
    with open(file_path, 'w') as f:
        json.dump(state, f)
    return jsonify({'success': True, 'name': state_name})

@app.route('/load_work_state/<state_name>', methods=['GET'])
def load_work_state(state_name):
    file_path = os.path.join(SAVE_FOLDER, f"{state_name}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            work_state = json.load(f)
        return jsonify(work_state)
    else:
        return jsonify({'error': 'Work state not found'}), 404

@app.route('/get_saved_states', methods=['GET'])
def get_saved_states():
    saved_states = [f.split('.')[0] for f in os.listdir(SAVE_FOLDER) if f.endswith('.json')]
    return jsonify(saved_states)

@app.route('/')
def index():
    videos = get_valid_videos()
    total_duration = sum(VideoFileClip(os.path.join(UPLOAD_FOLDER, video)).duration for video in videos)
    return render_template('index.html', videos=videos, total_duration=total_duration)

@app.route('/video_info/<filename>')
def get_video_info(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'ファイルが見つかりません'}), 404
    
    try:
        clip = VideoFileClip(file_path)
        
        # FFprobeを使用してメタデータを取得
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        metadata = json.loads(result.stdout)
        
        # 撮影日時の取得を試みる
        creation_time = None
        for stream in metadata.get('streams', []):
            if 'tags' in stream:
                creation_time = stream['tags'].get('creation_time')
                if creation_time:
                    break
        
        if not creation_time:
            creation_time = metadata.get('format', {}).get('tags', {}).get('creation_time')
        
        if creation_time:
            # ISO 8601形式の日時文字列をUNIXタイムスタンプに変換
            creation_time = datetime.fromisoformat(creation_time.replace('Z', '+00:00')).timestamp()
        else:
            # メタデータに撮影日時が含まれていない場合はファイルの最終更新日時を使用
            creation_time = os.path.getmtime(file_path)
        
        info = {
            'filename': filename,
            'duration': clip.duration,
            'size': os.path.getsize(file_path),
            'resolution': f"{clip.w}x{clip.h}",
            'creation_time': creation_time,
            'upload_time': os.path.getmtime(file_path)
        }
        clip.close()
        return jsonify(info)
    except Exception as e:
        app.logger.error(f"動画情報の取得エラー: {str(e)}")
        return jsonify({'error': '動画情報の取得に失敗しました'}), 500

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        if 'videos' in session and filename in session['videos']:
            session['videos'].remove(filename)
            session.modified = True
        return jsonify({'success': True})
    return jsonify({'error': 'File not found'}, 404)

@app.route('/save_video_order', methods=['POST'])
def save_video_order():
    data = request.json
    video_order = data.get('video_order', [])
    
    if not all(video in session['videos'] for video in video_order):
        return jsonify({'success': False, 'error': 'Invalid video order'})
    
    session['videos'] = video_order
    session.modified = True
    return jsonify({'success': True})

@app.route('/task_status/<task_id>')
def task_status(task_id):
    task = process_video_task.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'status': task.info.get('status', '')
        }
    else:
        response = {
            'state': task.state,
            'status': str(task.info)
        }
    return jsonify(response)


def get_metadata_date(valid_files, metadata_source, custom_video_filename):
    app.logger.info(f"get_metadata_date called with metadata_source: {metadata_source}")
    app.logger.info(f"Custom video filename: {custom_video_filename}")
    
    if metadata_source == 'earliest':
        app.logger.info("Using earliest date")
        return min(get_video_creation_time(file) for file, _ in valid_files)
    elif metadata_source == 'latest':
        app.logger.info("Using latest date")
        return max(get_video_creation_time(file) for file, _ in valid_files)
    elif metadata_source == 'custom':
        app.logger.info("Using custom date")
        custom_file = next((file for file, _ in valid_files if os.path.basename(file) == custom_video_filename), None)
        if custom_file:
            return get_video_creation_time(custom_file)
    elif metadata_source == 'current':
        app.logger.info("Using current date")
        return datetime.now()
    
    app.logger.warning(f"Unexpected metadata_source: {metadata_source}. Using current time.")
    return datetime.now()


@app.route('/combine_videos', methods=['POST'])
def combine_videos():
    try:
        app.logger.info("Combine videos request received")
        data = request.json
        app.logger.info(f"Received data: {data}")  # 追加
        input_files = data.get('input_files', [])
        output_file = data.get('output_file')
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_file)
        split_duration = data.get('split_duration', 'none')
        resolution = data.get('resolution', '100')
        metadata_source = data.get('metadata_source', 'current')  # デフォルトを'current'に変更
        custom_video_filename = data.get('custom_video_filename')
        app.logger.info(f"Metadata source: {metadata_source}")
        app.logger.info(f"Custom video filename: {custom_video_filename}")


        app.logger.info(f"Input files: {input_files}")
        app.logger.info(f"Output file: {output_file}")
        app.logger.info(f"Split duration: {split_duration}")
        app.logger.info(f"Resolution: {resolution}")
        app.logger.info(f"Received metadata_source: {metadata_source}")
        app.logger.info(f"Received custom_video_filename: {custom_video_filename}")

        if not isinstance(input_files, list):
            return jsonify({'success': False, 'error': 'input_files must be a list'}), 400

        valid_files = []
        for file_info in input_files:
            if isinstance(file_info, dict):
                filename = file_info.get('filename')
                overlay = file_info.get('overlay', {})
            elif isinstance(file_info, str):
                filename = file_info
                overlay = {}
            else:
                continue

            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                if not validate_video_file(file_path):
                    return jsonify({'success': False, 'error': f'Invalid or corrupted video file: {filename}'}), 400
                valid_files.append((file_path, overlay))
        
        if not valid_files:
            return jsonify({'success': False, 'error': 'No valid input files found.'}), 400
        
        clips = []
        try:
            for file_path, overlay in valid_files:
                clip = VideoFileClip(file_path)
                
                if overlay:
                    text_clip = TextClip(overlay['text'], fontsize=int(overlay['font_size']), 
                                         font='Arial', color=overlay['color'])
                    text_clip = text_clip.set_position(overlay['position'])
                    if overlay['duration'] == 'full':
                        text_clip = text_clip.set_duration(clip.duration)
                    else:
                        text_clip = text_clip.set_duration(float(overlay['duration']))
                    clip = CompositeVideoClip([clip, text_clip])
                
                clips.append(clip)
            
            horizontal_clips = [clip for clip in clips if get_video_orientation(clip) == 'horizontal']
            target_height = min(clip.h for clip in horizontal_clips) if horizontal_clips else min(clip.h for clip in clips)

            resized_clips = [resize_clip(clip, target_height) for clip in clips]

            final_clip = concatenate_videoclips(resized_clips)

            if resolution != '100':
                scale_factor = int(resolution) / 100
                final_clip = final_clip.resize(width=int(final_clip.w * scale_factor))

            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_file)

            logger = MyBarLogger()
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=logger)
            logger.finish()
            
            app.logger.info("Combine videos processing completed")

            # 以下の2行を追加
            creation_time = get_metadata_date(valid_files, metadata_source, custom_video_filename)
            set_video_creation_time(output_path, creation_time)
            app.logger.info(f"Set creation time to: {creation_time}") 

            if split_duration != 'none':
                split_duration_seconds = int(float(split_duration) * 60)  # 分を秒に変換
                try:
                    split_files = split_video(output_path, split_duration_seconds)
                    return jsonify({'success': True, 'split_files': split_files, 'creation_time': creation_time.isoformat()})
                except Exception as e:
                    app.logger.error(f"Error in split_video: {str(e)}")
                    return jsonify({'success': True, 'output_file': output_file, 'split_error': str(e), 'creation_time': creation_time.isoformat()})
            else:
                return jsonify({'success': True, 'output_file': output_file, 'creation_time': creation_time.isoformat()})
        
        except Exception as e:
            app.logger.error(f"Error in video processing: {str(e)}")
            app.logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500
        finally:
            for clip in clips:
                clip.close()

    except Exception as e:
        app.logger.error(f"Error in combine_videos: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': f"An error occurred while processing your request: {str(e)}", 'traceback': traceback.format_exc()}), 500
    app.logger.info("Combine videos request received")
    try:
        data = request.json
        input_files = data.get('input_files', [])
        output_file = data.get('output_file')
        split_duration = data.get('split_duration', 'none')
        resolution = data.get('resolution', '100')
        metadata_source = data.get('metadata_source', 'earliest')
        custom_video_filename = data.get('custom_video_filename')

        app.logger.info(f"Input files: {input_files}")
        app.logger.info(f"Output file: {output_file}")
        app.logger.info(f"Split duration: {split_duration}")
        app.logger.info(f"Resolution: {resolution}")

        if not isinstance(input_files, list):
            return jsonify({'success': False, 'error': 'input_files must be a list'}), 400

        valid_files = []
        for file_info in input_files:
            if isinstance(file_info, dict):
                filename = file_info.get('filename')
                overlay = file_info.get('overlay', {})
            elif isinstance(file_info, str):
                filename = file_info
                overlay = {}
            else:
                continue

            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                if not validate_video_file(file_path):
                    return jsonify({'success': False, 'error': f'Invalid or corrupted video file: {filename}'}), 400
                valid_files.append((file_path, overlay))
        
        if not valid_files:
            return jsonify({'success': False, 'error': 'No valid input files found.'}), 400
        
        clips = []
        try:
            for file_path, overlay in valid_files:
                clip = VideoFileClip(file_path)
                
                if overlay:
                    text_clip = TextClip(overlay['text'], fontsize=int(overlay['font_size']), 
                                         font='Arial', color=overlay['color'])
                    text_clip = text_clip.set_position(overlay['position'])
                    if overlay['duration'] == 'full':
                        text_clip = text_clip.set_duration(clip.duration)
                    else:
                        text_clip = text_clip.set_duration(float(overlay['duration']))
                    clip = CompositeVideoClip([clip, text_clip])
                
                clips.append(clip)
            
            horizontal_clips = [clip for clip in clips if get_video_orientation(clip) == 'horizontal']
            target_height = min(clip.h for clip in horizontal_clips) if horizontal_clips else min(clip.h for clip in clips)

            resized_clips = [resize_clip(clip, target_height) for clip in clips]

            final_clip = concatenate_videoclips(resized_clips)

            if resolution != '100':
                scale_factor = int(resolution) / 100
                final_clip = final_clip.resize(width=int(final_clip.w * scale_factor))

            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_file)

            logger = MyBarLogger()
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=logger)
            logger.finish()
            
            app.logger.info("Combine videos processing completed")

            if split_duration != 'none':
                split_duration_seconds = int(float(split_duration) * 60)  # 分を秒に変換
                try:
                    split_files = split_video(output_path, split_duration_seconds)
                    return jsonify({'success': True, 'split_files': split_files})
                except Exception as e:
                    app.logger.error(f"Error in split_video: {str(e)}")
                    return jsonify({'success': True, 'output_file': output_file, 'split_error': str(e)})
            else:
                return jsonify({'success': True, 'output_file': output_file})
            creation_date = get_metadata_date(valid_files, metadata_source, custom_video_filename)
            set_video_metadata(output_path, creation_date)
        
        except Exception as e:
            app.logger.error(f"Error in video processing: {str(e)}")
            app.logger.error(traceback.format_exc())
            return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500
        finally:
            for clip in clips:
                clip.close()

    except Exception as e:
        app.logger.error(f"Error in combine_videos: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': f"An error occurred while processing your request: {str(e)}", 'traceback': traceback.format_exc()}), 500





def get_video_creation_time(file_path):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    
    creation_time = None
    for stream in metadata.get('streams', []):
        if 'tags' in stream:
            creation_time = stream['tags'].get('creation_time')
            if creation_time:
                break
    
    if not creation_time:
        creation_time = metadata.get('format', {}).get('tags', {}).get('creation_time')
    
    if creation_time:
        return datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
    else:
        app.logger.warning(f"No creation time found in metadata for {file_path}. Using file modification time.")
        return datetime.fromtimestamp(os.path.getmtime(file_path))

def set_video_metadata(video_path, creation_date):
    # FFmpegを使用してメタデータを設定
    temp_output = video_path + '.temp' + os.path.splitext(video_path)[1]
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-c', 'copy',
        '-metadata', f'creation_time={creation_date.isoformat()}Z',
        temp_output
    ]
    subprocess.run(cmd, check=True)
    
    # 元のファイルを置き換え
    os.replace(temp_output, video_path)

def set_video_creation_time(video_path, creation_time):
    # 日本のタイムゾーンを設定
    japan_tz = pytz.timezone('Asia/Tokyo')
    
    # 入力がnaive datetimeの場合、JSTとして解釈
    if creation_time.tzinfo is None:
        creation_time = japan_tz.localize(creation_time)
    else:
        # UTCからJSTに変換
        creation_time = creation_time.astimezone(japan_tz)
    
    # FFmpegのメタデータ用にUTC時間に変換
    creation_time_utc = creation_time.astimezone(pytz.UTC)
    creation_time_str = creation_time_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    
    temp_output = video_path + '.temp' + os.path.splitext(video_path)[1]
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-c', 'copy',
        '-metadata', f'creation_time={creation_time_str}',
        '-metadata', f'date={creation_time_str}',  # dateメタデータも追加
        '-movflags', 'use_metadata_tags',
        temp_output
    ]
    app.logger.info(f"Setting creation time to: {creation_time_str} (UTC) for {video_path}")
    subprocess.run(cmd, check=True)
    
    os.replace(temp_output, video_path)
    
    # ファイルシステムの作成日も更新（ローカル時間を使用）
    os.utime(video_path, (creation_time.timestamp(), creation_time.timestamp()))
    
    app.logger.info(f"Video creation time set to: {creation_time.strftime('%Y-%m-%dT%H:%M:%S %Z')} for {video_path}")

def check_metadata(video_path):
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    
    creation_time = metadata['format'].get('tags', {}).get('creation_time')
    app.logger.info(f"Metadata check for {video_path}: creation_time = {creation_time}")
    
    return creation_time

def split_video(input_file, split_duration):
    base, ext = os.path.splitext(input_file)
    output_template = f"{base}_part_%03d{ext}"

    # 入力ファイルのメタデータを取得
    probe_cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        input_file
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    metadata = json.loads(probe_result.stdout)
    creation_time = metadata['format']['tags'].get('creation_time')
    
    command = [
        'ffmpeg',
        '-i', input_file,
        '-c', 'copy',
        '-f', 'segment',
        '-segment_time', str(split_duration),
        '-reset_timestamps', '1',
        '-avoid_negative_ts', 'make_zero',
        '-map_metadata', '0',  # メタデータをコピー
        '-segment_start_number', '0'
    ]
    
    # 作成時間をメタデータとして追加
    if creation_time:
        command.extend(['-metadata', f'creation_time={creation_time}'])

    command.append(output_template)
    
    app.logger.info(f"Executing FFmpeg command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        app.logger.info(f"FFmpeg stdout: {result.stdout}")
        app.logger.info(f"FFmpeg stderr: {result.stderr}")
    except subprocess.CalledProcessError as e:
        app.logger.error(f"FFmpeg command failed: {e}")
        app.logger.error(f"FFmpeg stderr: {e.stderr}")
        raise
    
    split_files = [os.path.basename(f) for f in sorted(glob.glob(f"{base}_part_*{ext}"))]
    
    # 各分割ファイルのメタデータを確認し、黒いフレームを削除
    for split_file in split_files:
        split_file_path = os.path.join(os.path.dirname(input_file), split_file)
        check_and_set_metadata(split_file_path, creation_time)
        remove_black_frames_from_start(split_file_path)
    
    return split_files

def check_and_set_metadata(file_path, original_creation_time):
    probe_cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        file_path
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    metadata = json.loads(probe_result.stdout)
    current_creation_time = metadata['format']['tags'].get('creation_time')

    if current_creation_time != original_creation_time:
        app.logger.info(f"Setting correct creation time for {file_path}")
        set_video_creation_time(file_path, datetime.fromisoformat(original_creation_time.replace('Z', '+00:00')))
    else:
        app.logger.info(f"Correct creation time already set for {file_path}")

    # ファイルシステムの作成日時も更新
    creation_time_obj = datetime.fromisoformat(original_creation_time.replace('Z', '+00:00'))
    os.utime(file_path, (creation_time_obj.timestamp(), creation_time_obj.timestamp()))

def remove_black_frames_from_start(video_file):
    output_file = video_file.replace('.mov', '_cleaned.mov')
    
    # 元のファイルのメタデータを取得
    probe_cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_file
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    metadata = json.loads(probe_result.stdout)
    creation_time = metadata['format']['tags'].get('creation_time')

    command = [
        'ffmpeg',
        '-i', video_file,
        '-vf', 'select=\'not(eq(n,0)+eq(n,1))\',setpts=N/FRAME_RATE/TB',
        '-af', 'aselect=\'not(eq(n,0)+eq(n,1))\',asetpts=N/SR/TB',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-c:a', 'aac',
        '-map_metadata', '0',
        '-metadata:s:v:0', 'rotate=0',
        '-y',
        output_file
    ]
    
    if creation_time:
        command.extend(['-metadata', f'creation_time={creation_time}'])
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        app.logger.info(f"FFmpeg stdout: {result.stdout}")
        app.logger.info(f"FFmpeg stderr: {result.stderr}")
        
        # ファイルシステムの日時を設定
        if creation_time:
            creation_time_obj = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
            os.utime(output_file, (creation_time_obj.timestamp(), creation_time_obj.timestamp()))
        
        shutil.copy2(output_file, video_file)  # メタデータを保持してコピー
        os.remove(output_file)  # 一時ファイルを削除
        
        app.logger.info(f"Removed black frames from {video_file}")
    except subprocess.CalledProcessError as e:
        app.logger.error(f"FFmpeg command failed: {e}")
        app.logger.error(f"FFmpeg stderr: {e.stderr}")
        raise

    # メタデータが正しく設定されたか確認
    check_metadata(video_file)

def set_creation_time_for_split(video_path, base_creation_time, part_number):
    creation_time = base_creation_time + timedelta(seconds=part_number)
    creation_time_str = creation_time.strftime("%Y-%m-%dT%H:%M:%S")
    temp_output = video_path + '.temp' + os.path.splitext(video_path)[1]
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-c', 'copy',
        '-metadata', f'creation_time={creation_time_str}',
        temp_output
    ]
    app.logger.info(f"Setting creation time to: {creation_time_str} for {video_path}")
    subprocess.run(cmd, check=True)
    
    os.replace(temp_output, video_path)
    
    # ファイルシステムの作成日も更新
    os.utime(video_path, (creation_time.timestamp(), creation_time.timestamp()))
    
    app.logger.info(f"Video creation time set to: {creation_time_str} for {video_path}")

@app.route('/clear_session', methods=['POST'])
def clear_session():
    app.logger.info("Clear session request received")
    try:
        session.clear()
        # アップロードフォルダ内のファイルも削除する場合
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                app.logger.error(f"Error deleting file {file_path}: {str(e)}")
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error clearing session: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/process_videos', methods=['POST'])
def process_videos():
    try:
        app.logger.info("Process videos request received")
        data = request.json
        app.logger.info(f"Received data: {data}")
        input_files = data.get('input_files', [])
        output_file = data.get('output_file')
        split_duration = data.get('split_duration', 'none')
        resolution = data.get('resolution', '100')
        metadata_source = data.get('metadata_source', 'current')
        custom_video_filename = data.get('custom_video_filename')

        if not input_files:
            return jsonify({'success': False, 'error': 'No input files provided'}), 400

        valid_files = []
        for file_info in input_files:
            filename = file_info.get('filename')
            overlay = file_info.get('overlay', {})
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                if not validate_video_file(file_path):
                    return jsonify({'success': False, 'error': f'Invalid or corrupted video file: {filename}'}), 400
                valid_files.append((file_path, overlay))

        if not valid_files:
            return jsonify({'success': False, 'error': 'No valid input files found.'}), 400

        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_file)

        # 1本の動画の場合は単純にコピー
        if len(valid_files) == 1:
            shutil.copy(valid_files[0][0], output_path)
        else:
            # 複数動画の結合処理（既存のcombine_videos関数を使用）
            combine_videos_logic(valid_files, output_path, resolution)
       ## 作成日の設定
        creation_time = get_metadata_date(valid_files, metadata_source, custom_video_filename)
        set_video_creation_time(output_path, creation_time)

        # 分割処理
        if split_duration != 'none':
            split_duration_seconds = int(float(split_duration) * 60)
            split_files = split_video(output_path, split_duration_seconds)
            
            # 分割したファイルの作成日時を確認・設定
            for split_file in split_files:
                split_file_path = os.path.join(app.config['OUTPUT_FOLDER'], split_file)
                check_and_set_metadata(split_file_path, creation_time.isoformat() + 'Z')
            
            return jsonify({'success': True, 'split_files': split_files, 'creation_time': creation_time.isoformat()})
        else:
            return jsonify({'success': True, 'output_file': output_file, 'creation_time': creation_time.isoformat()})

    except Exception as e:
        app.logger.error(f"Error in process_videos: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500

def change_video_resolution(video_path, resolution_percentage):
    output_path = video_path + '.temp.mp4'
    scale_factor = int(resolution_percentage) / 100
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vf', f'scale=iw*{scale_factor}:ih*{scale_factor}',
        '-c:a', 'copy',
        output_path
    ]
    subprocess.run(cmd, check=True)
    os.replace(output_path, video_path)
    try:
        app.logger.info("Process videos request received")
        data = request.json
        app.logger.info(f"Received data: {data}")
        input_files = data.get('input_files', [])
        output_file = data.get('output_file')
        split_duration = data.get('split_duration', 'none')
        resolution = data.get('resolution', '100')
        metadata_source = data.get('metadata_source', 'current')
        custom_video_filename = data.get('custom_video_filename')

        if not input_files:
            return jsonify({'success': False, 'error': 'No input files provided'}), 400

        valid_files = []
        for file_info in input_files:
            filename = file_info.get('filename')
            overlay = file_info.get('overlay', {})
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                if not validate_video_file(file_path):
                    return jsonify({'success': False, 'error': f'Invalid or corrupted video file: {filename}'}), 400
                valid_files.append((file_path, overlay))

        if not valid_files:
            return jsonify({'success': False, 'error': 'No valid input files found.'}), 400

        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_file)

        # 1本の動画の場合は単純にコピー
        if len(valid_files) == 1:
            shutil.copy(valid_files[0][0], output_path)
        else:
            # 複数動画の結合処理（既存のcombine_videos関数を使用）
            combine_videos_logic(valid_files, output_path, resolution)

        # 作成日の設定
        creation_time = get_metadata_date(valid_files, metadata_source, custom_video_filename)
        set_video_creation_time(output_path, creation_time)

        # 解像度の変更
        if resolution != '100':
            change_video_resolution(output_path, resolution)

        # 動画の分割
        if split_duration != 'none':
            split_duration_seconds = int(float(split_duration) * 60)
            split_files = split_video(output_path, split_duration_seconds)
            return jsonify({'success': True, 'split_files': split_files, 'creation_time': creation_time.isoformat()})

        return jsonify({'success': True, 'output_file': output_file, 'creation_time': creation_time.isoformat()})

    except Exception as e:
        app.logger.error(f"Error in process_videos: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500

def change_video_resolution(video_path, resolution_percentage):
    output_path = video_path + '.temp.mp4'
    scale_factor = int(resolution_percentage) / 100
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vf', f'scale=iw*{scale_factor}:ih*{scale_factor}',
        '-c:a', 'copy',
        output_path
    ]
    subprocess.run(cmd, check=True)
    os.replace(output_path, video_path)


@app.route('/process_audio', methods=['POST'])
def process_audio():
    try:
        data = request.json
        videos = data.get('videos', [])
        settings = data.get('settings', {})

        if not videos:
            return jsonify({'success': False, 'error': 'No videos provided'}), 400

        print(f"Processing audio for videos: {videos}")
        print(f"Audio settings: {settings}")

        for video in videos:
            try:
                apply_audio_processing(video, settings)
                print(f"Audio processing completed for {video}")
            except Exception as e:
                print(f"Error processing {video}: {str(e)}")
                return jsonify({'success': False, 'error': f"Error processing {video}: {str(e)}"}), 500

        print("Audio processing completed for all videos")
        return jsonify({'success': True, 'message': f'Processed {len(videos)} videos successfully'})
    except Exception as e:
        app.logger.error(f"Error in process_audio: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/audio_processing_status', methods=['POST'])
def audio_processing_status():
    task_ids = request.json.get('task_ids', [])
    results = []
    for task_id in task_ids:
        task = process_audio_task.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            results.append(task.result)
        elif task.state == 'FAILURE':
            results.append({'status': 'error', 'error': str(task.result)})
        else:
            results.append({'status': 'pending'})
    return jsonify(results)

@app.route('/preview_audio_processing', methods=['POST'])
def preview_audio_processing():
    data = request.json
    target_lufs = float(data['targetLufs'])
    intensity = data['intensity']
    preserve_quiet = data['preserveQuiet']

    if not session['videos']:
        return jsonify({'success': False, 'error': 'No videos available for preview'})

    input_path = os.path.join(app.config['UPLOAD_FOLDER'], session['videos'][0])
    preview_output_path = os.path.join(app.config['TEMP_FOLDER'], f"preview_{session['videos'][0]}")

    try:
        adaptive_audio_processing(input_path, preview_output_path, target_lufs, intensity, preserve_quiet)
        return jsonify({'success': True, 'previewUrl': f"/temp/{os.path.basename(preview_output_path)}"})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def apply_audio_processing(video, settings):
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], video)
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"processed_{video}")
    
    target_lufs = settings.get('targetLufs', -14)

    ffmpeg_command = [
        "ffmpeg", "-i", input_path,
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-ar", "44100",  # サンプリングレートを44.1kHzに維持
        "-c:v", "copy",
        "-c:a", "aac",
        "-map_metadata", "0",
        "-movflags", "+faststart",
        output_path
    ]
    # FFmpegコマンドの実行
    try:
        result = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        print(f"FFmpeg command: {' '.join(ffmpeg_command)}")
        print(f"FFmpeg output: {result.stdout}")
        print(f"FFmpeg error: {result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr}")
        raise Exception(f"FFmpeg processing failed: {e.stderr}")

    # 処理後のファイルを元のファイルに置き換える
    os.replace(output_path, input_path)
    check_command = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "default=noprint_wrappers=1", output_path]
    result = subprocess.run(check_command, capture_output=True, text=True)
    print(f"FFprobe output for {os.path.basename(output_path)}:")
    print(result.stdout)

@app.route('/audio_preview', methods=['POST'])
def audio_preview():
    try:
        data = request.json
        video = data.get('video')
        settings = data.get('settings')

        if not video:
            return jsonify({'error': 'No video provided'}), 400

        input_path = os.path.join(app.config['UPLOAD_FOLDER'], video)
        
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            output_path = temp_file.name

        # 10秒のプレビューを作成
        ffmpeg_command = [
            "ffmpeg", "-i", input_path,
            "-ss", "00:00:10",  # 10秒からスタート
            "-t", "10",  # 10秒間
            "-af", f"loudnorm=I={settings['targetLufs']}:TP=-1.5:LRA=11"
        ]

        if settings['noiseReduction'] > 0:
            ffmpeg_command[-1] += f",afftdn=nf=-{settings['noiseReduction']}"
        
        if settings['dehummer'] > 0:
            ffmpeg_command[-1] += f",highpass=f=60,lowpass=f=240"

        ffmpeg_command.extend(["-vn", output_path])

        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)

        # 一時ファイルのパスを返す
        preview_url = f"/audio_preview_file/{os.path.basename(output_path)}"
        return jsonify({'preview_url': preview_url})

    except Exception as e:
        app.logger.error(f"Error in audio_preview: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/audio_preview_file/<filename>')
def audio_preview_file(filename):
    return send_from_directory(tempfile.gettempdir(), filename)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}")
    return jsonify({"error": str(e)}), 500

@app.errorhandler(400)
def bad_request(e):
    return jsonify(error=str(e)), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify(error=str(e)), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify(error=str(e)), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}")
    return "Internal Server Error", 500

@app.errorhandler(416)
def range_not_satisfiable(error):
    app.logger.error(f"Range Not Satisfiable error: {error}")
    return "Requested range not satisfiable", 416

@app.route('/video_metadata/<filename>')
def video_metadata(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        abort(404, description="File not found")
    
    file_size = os.path.getsize(file_path)
    
    return jsonify({
        'filename': filename,
        'size': file_size,
    })

@app.route('/get_overlaid_videos', methods=['GET'])
def get_overlaid_videos():
    overlaid_videos = [f for f in os.listdir(app.config['OUTPUT_FOLDER']) if f.startswith('overlay_')]
    return jsonify({'overlaid_videos': overlaid_videos})

@app.route('/use_overlaid_video', methods=['POST'])
def use_overlaid_video():
    data = request.json
    original_filename = data.get('original_filename')
    overlaid_filename = data.get('overlaid_filename')
    
    if not original_filename or not overlaid_filename:
        return jsonify({'success': False, 'error': 'Invalid filenames provided'}), 400
    
    original_path = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)
    overlaid_path = os.path.join(app.config['OUTPUT_FOLDER'], overlaid_filename)
    
    if not os.path.exists(overlaid_path):
        return jsonify({'success': False, 'error': 'Overlaid video not found'}), 404
    
    # オーバーレイされた動画を元の動画として使用
    shutil.copy(overlaid_path, original_path)
    
    return jsonify({'success': True, 'message': 'Overlaid video is now used as the main video'})

@app.route('/add_overlay_info', methods=['POST'])
def add_overlay_info():
    data = request.json
    video_filename = data['video_filename']
    overlay_info = data['overlay_info']
    
    # オーバーレイ情報を保存（例：メモリ内辞書を使用）
    if 'overlay_infos' not in session:
        session['overlay_infos'] = {}
    if video_filename not in session['overlay_infos']:
        session['overlay_infos'][video_filename] = []
    session['overlay_infos'][video_filename].append(overlay_info)
    session.modified = True

    return jsonify({'success': True})

def create_text_clip(overlay_info, video_size):
    text_clip = TextClip(overlay_info['text'], fontsize=overlay_info['font_size'], 
                         color=overlay_info['color'], font=overlay_info['font'])
    text_clip = text_clip.set_position(overlay_info['position'])
    if overlay_info['duration'] != 'full':
        text_clip = text_clip.set_duration(float(overlay_info['duration']))
    return text_clip

def validate_video_file(file_path):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', 
                                 '-count_packets', '-show_entries', 'stream=nb_read_packets', 
                                 '-of', 'csv=p=0', file_path], 
                                capture_output=True, text=True, check=True)
        return int(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False

@app.errorhandler(500)
def internal_error(error):
    app.logger.error('Server Error: %s', str(error))
    return jsonify(error=str(error)), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
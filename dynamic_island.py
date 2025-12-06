import sys
import asyncio
import threading
import math
import time
import base64
import json
import os
import winreg
import numpy as np


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)
from PyQt5.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu, QAction,
                             QVBoxLayout, QHBoxLayout, QLabel, QSlider, QCheckBox, 
                             QPushButton, QTabWidget, QFrame, QSpinBox, QComboBox,
                             QScrollArea, QScroller)
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QRectF, QEasingCurve, QTimer, pyqtSignal, QPoint, QByteArray
from PyQt5.QtGui import QPainter, QBrush, QColor, QPixmap, QPainterPath, QImage, QLinearGradient, QFont, QPen, QFontDatabase, QIcon


try:
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
    from winsdk.windows.storage.streams import DataReader, Buffer, InputStreamOptions
    MEDIA_AVAILABLE = True
except ImportError:
    MEDIA_AVAILABLE = False

try:
    import pyaudiowpatch as pyaudio
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


class AudioAnalyzer:
    def __init__(self):
        self.p = None
        self.stream = None
        self.running = False
        self.bands = [0.0] * 12
        self.lock = threading.Lock()
        self.freq_ranges = [
            (20, 80), (80, 160), (160, 300), (300, 500),
            (500, 800), (800, 1200), (1200, 2000), (2000, 3500),
            (3500, 6000), (6000, 10000), (10000, 14000), (14000, 20000)
        ]

    def start(self):
        if not AUDIO_AVAILABLE or self.running:
            return
        self.running = True
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def get_bands(self):
        with self.lock:
            return self.bands.copy()

    def _capture_loop(self):
        try:
            self.p = pyaudio.PyAudio()
            wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers["isLoopbackDevice"]:
                for loopback in self.p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break
            rate = int(default_speakers["defaultSampleRate"])
            channels = default_speakers["maxInputChannels"]
            chunk = 1024
            self.stream = self.p.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True, input_device_index=default_speakers["index"], frames_per_buffer=chunk)
            while self.running:
                try:
                    data = self.stream.read(chunk, exception_on_overflow=False)
                    audio_data = np.frombuffer(data, dtype=np.float32)
                    if channels > 1:
                        audio_data = audio_data.reshape(-1, channels).mean(axis=1)
                    fft = np.abs(np.fft.rfft(audio_data))
                    freqs = np.fft.rfftfreq(len(audio_data), 1.0 / rate)
                    
                    fft = fft / len(audio_data)
                    
                    band_multipliers = [0.8, 1.0, 1.3, 1.6, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
                    
                    new_bands = []
                    for idx, (low, high) in enumerate(self.freq_ranges):
                        mask = (freqs >= low) & (freqs < high)
                        if mask.any():
                            val = np.mean(fft[mask])
                            multiplier = band_multipliers[idx] if idx < len(band_multipliers) else 1.0
                            level = min(1.0, max(0.0, val * multiplier * 20.0))
                        else:
                            level = 0.0
                        new_bands.append(level)
                    with self.lock:
                        for i in range(len(new_bands)):
                            self.bands[i] = self.bands[i] * 0.7 + new_bands[i] * 0.3
                except:
                    pass
        except:
            pass
        finally:
            if self.stream:
                self.stream.close()
            if self.p:
                self.p.terminate()


class DynamicIsland(QWidget):
    media_updated = pyqtSignal(bool, object, str, str, float, float)

    def __init__(self):
        super().__init__()
        
        self.config = load_config()
        
        self.base_width = self.config.get('idle_width', 150)
        self.base_height = 40
        self.expanded_width = 330
        self.expanded_height = 200
        self.media_width = self.config.get('media_width', 200)
        self.now_width = self.base_width
        self.now_height = self.base_height
        self.is_media_playing = False
        self.is_expanded = False
        self.album_art = None
        self.checking_media = False
        self.eq_bars = [0.1] * 12
        self.show_equalizer = self.config.get('show_equalizer', True)
        self.eq_color_from_art = self.config.get('eq_color_from_art', True)
        self.text_animation_enabled = self.config.get('text_animation', True)
        self.button_animation_enabled = self.config.get('button_animation', True)
        self.flip_animation_enabled = self.config.get('flip_animation', True)
        self.top_offset = self.config.get('top_offset', 15)
        self.bounce_enabled = self.config.get('bounce_effect', True)
        self.animation_speed = self.config.get('animation_speed', 100) / 100.0
        self.corner_radius = self.config.get('corner_radius', 20)
        self.corner_radius_current = self.corner_radius
        self.corner_radius_target = self.corner_radius
        self.compact_corner_radius_current = self.config.get('compact_corner_radius', 20)
        self.compact_corner_radius_target = self.config.get('compact_corner_radius', 20)
        self.click_to_open_app = self.config.get('click_to_open_app', True)
        self.long_press_duration = self.config.get('long_press_duration', 250)
        self.show_time_remaining = self.config.get('show_time_remaining', True)
        self.eq_bar_count = self.config.get('eq_bar_count', 6)
        self.eq_sensitivity = self.config.get('eq_sensitivity', 100)
        self.text_animation_style = self.config.get('text_animation_style', 0)
        self.compact_corner_radius = self.config.get('compact_corner_radius', 20)
        self.double_click_action = self.config.get('double_click_action', 0)
        self.show_progress_bar = self.config.get('show_progress_bar', True)
        self.autohide = self.config.get('autohide', False)
        self.monitor_index = self.config.get('monitor', 0)
        
        self.typewriter_index = 0
        self.typewriter_timer = 0
        
        scale = self.config.get('size_scale', 100) / 100.0
        idle_width = self.config.get('idle_width', 150)
        media_width = self.config.get('media_width', 200)
        self.base_width = int(idle_width * scale)
        self.base_height = int(40 * scale)
        self.expanded_width = 330
        self.expanded_height = 200
        self.media_width = int(media_width * scale)
        self.eq_color_top = QColor(255, 255, 255)
        self.eq_color_bottom = QColor(255, 255, 255)
        self.eq_color_top_target = QColor(255, 255, 255)
        self.eq_color_bottom_target = QColor(255, 255, 255)
        self.audio_analyzer = AudioAnalyzer()
        self.flip_angle = 0.0
        self.flip_animating = False
        self.new_album_art = None
        self.new_eq_colors = None
        self.last_thumbnail_hash = None
        self.track_title = ""
        self.track_artist = ""
        self.old_title = ""
        self.old_artist = ""
        self.text_anim_progress = 1.0
        self.text_animating = False
        self.title_scroll_offset = 0.0
        self.artist_scroll_offset = 0.0
        self.title_needs_scroll = False
        self.artist_needs_scroll = False
        self.scroll_pause_start = 0.0
        self.scroll_start_time = 0.0
        self.title_scrolling = False
        self.artist_scrolling = False
        self._title_text_width = 0
        self._artist_text_width = 0
        self.track_position = 0.0
        self.track_duration = 0.0
        self.server_position = 0.0
        self.last_update_time = time.time()
        self.media_session = None
        self.press_timer = None
        self.expanded_y_offset = 20
        self.is_pressing = False
        self.dragging_slider = False
        self.slider_rect = None
        self.is_hidden = False
        self.has_media_session = False
        self.pause_progress = 1.0
        

        self.play_pause_scale = 1.0
        self.play_pause_animating = False
        self.play_pause_target_playing = False
        self.play_pause_shrinking = True
        
        self.prev_scale = 1.0
        self.prev_offset = 0.0
        self.prev_animating = False
        self.next_scale = 1.0
        self.next_offset = 0.0
        self.next_animating = False
        
        self.icon_play = QPixmap(resource_path("Play.png"))
        self.icon_pause = QPixmap(resource_path("Pause.png"))
        self.icon_prev = QPixmap(resource_path("Previous.png"))
        self.icon_next = QPixmap(resource_path("Next.png"))
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screens = QApplication.screens()
        screen = screens[self.monitor_index].geometry() if self.monitor_index < len(screens) else QApplication.primaryScreen().geometry()
        self.setGeometry(screen.x() + (screen.width() - self.base_width) // 2, screen.y() - self.base_height - 20, self.base_width, self.base_height)
        
        self.animation = QPropertyAnimation(self, b"geometry")
        base_duration = 350
        self.animation.setDuration(int(base_duration / self.animation_speed))
        if self.bounce_enabled:
            self.animation.setEasingCurve(QEasingCurve.OutBack)
        else:
            self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self.on_animation_finished)
        self.expanding = False
        self.media_updated.connect(self.on_media_updated)
        
        self._startup_animation_done = False
        QTimer.singleShot(100, self._animate_startup)
        
        if MEDIA_AVAILABLE:
            self.media_timer = QTimer()
            self.media_timer.timeout.connect(self.check_media)
            self.media_timer.start(100)
        
        self.eq_timer = QTimer()
        self.eq_timer.timeout.connect(self.update_equalizer)
        self.eq_timer.start(30)
        self.flip_timer = QTimer()
        self.flip_timer.timeout.connect(self.update_flip)
        self.flip_timer.start(16)
    
    def _animate_startup(self):
        if self._startup_animation_done:
            return
        self._startup_animation_done = True
        screen = self.get_current_screen().geometry()
        x = screen.x() + (screen.width() - self.base_width) // 2
        y = screen.y() + self.top_offset
        
        self.animation.stop()
        self.animation.setDuration(500)
        self.animation.setEasingCurve(QEasingCurve.OutBack)
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(x, y, self.base_width, self.base_height))
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setBrush(QBrush(QColor(0, 0, 0)))
        painter.setPen(Qt.NoPen)
        
        w, h = self.width(), self.height()
        
        if self.is_expanded or h > self.base_height + 10:
            progress = min(1.0, max(0.0, (h - self.base_height) / (self.expanded_height - self.base_height)))
        else:
            progress = 0.0

        compact_radius = min(h // 2, self.compact_corner_radius_current)
        expanded_radius = self.corner_radius_current
        radius = compact_radius + (expanded_radius - compact_radius) * progress
        painter.drawRoundedRect(self.rect(), radius, radius)
        
        self.draw_interpolated(painter, progress)

    def lerp(self, a, b, t):
        return a + (b - a) * t
    
    def draw_interpolated(self, painter, progress):
        w, h = self.width(), self.height()
        
        compact_img_size = h - 12
        compact_img_x = 8
        compact_img_y = 6
        
        expanded_img_size = 60
        expanded_img_x = 15
        expanded_img_y = 22
        
        img_size = self.lerp(compact_img_size, expanded_img_size, progress)
        img_x = self.lerp(compact_img_x, expanded_img_x, progress)
        img_y = self.lerp(compact_img_y, expanded_img_y, progress)
        img_radius = self.lerp(6, 8, progress)
        
        if self.album_art and (self.is_media_playing or self.has_media_session):
            scale_x = abs(math.cos(math.radians(self.flip_angle)))
            if scale_x < 0.01:
                scale_x = 0.01
            
            if progress == 0 and self.pause_progress > 0.01:
                original_size = img_size
                pause_scale = 1.0 - (self.pause_progress * 0.15)
                img_size = original_size * pause_scale
                img_y = (h - img_size) / 2
            
            center_x = img_x + img_size / 2
            center_y = img_y + img_size / 2
            
            painter.save()
            painter.translate(center_x, center_y)
            painter.scale(scale_x, 1.0)
            painter.translate(-img_size / 2, -img_size / 2)
            
            size_int = int(img_size)
            scaled = self.album_art.scaled(size_int, size_int, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            
            if scaled.width() > size_int or scaled.height() > size_int:
                x_off = (scaled.width() - size_int) // 2
                y_off = (scaled.height() - size_int) // 2
                scaled = scaled.copy(x_off, y_off, size_int, size_int)
            
            if self.pause_progress > 0.01:
                dim_factor = 1.0 - (self.pause_progress * 0.4)
                painter.setOpacity(dim_factor)
            
            path = QPainterPath()
            path.addRoundedRect(0, 0, img_size, img_size, img_radius, img_radius)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.setOpacity(1.0)
            
            painter.restore()
        
        eq_opacity = 1.0 - self.pause_progress
        if eq_opacity > 0.01 and self.show_equalizer:
            painter.setClipRect(self.rect())
            painter.setOpacity(eq_opacity)
            
            num_bars = min(self.eq_bar_count, len(self.eq_bars))
            
            compact_bar_w, compact_bar_gap = 3, 2
            compact_eq_max_h = h - 16
            compact_total_w = num_bars * compact_bar_w + (num_bars - 1) * compact_bar_gap
            compact_eq_x = w - compact_total_w - 12
            compact_eq_y = h / 2
            
            expanded_bar_w, expanded_bar_gap = 4, 3
            expanded_eq_max_h = 50
            expanded_total_w = num_bars * expanded_bar_w + (num_bars - 1) * expanded_bar_gap
            expanded_eq_x = w - 15 - expanded_total_w
            expanded_eq_y = 22 + expanded_eq_max_h / 2
            
            bar_w = self.lerp(compact_bar_w, expanded_bar_w, progress)
            bar_gap = self.lerp(compact_bar_gap, expanded_bar_gap, progress)
            eq_max_h = self.lerp(compact_eq_max_h, expanded_eq_max_h, progress)
            eq_x = self.lerp(compact_eq_x, expanded_eq_x, progress)
            eq_y = self.lerp(compact_eq_y, expanded_eq_y, progress)
            
            for i in range(num_bars):
                level = self.eq_bars[i] if i < len(self.eq_bars) else 0.1
                bar_height = max(3, int(eq_max_h * level))
                x = eq_x + i * (bar_w + bar_gap)
                y = eq_y - bar_height / 2
                gradient = QLinearGradient(x, y, x, y + bar_height)
                gradient.setColorAt(0, self.eq_color_top)
                gradient.setColorAt(1, self.eq_color_bottom)
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_height), 1, 1)
            
            painter.setOpacity(1.0)
        
        if progress < 0.3 and self.show_progress_bar and self.has_media_session and self.track_duration > 0:
            bar_opacity = 1.0 - (progress / 0.3)
            painter.setOpacity(bar_opacity * 0.6)
            
            bar_height = 2
            bar_y = h - 2
            bar_margin = 14 
            bar_width = w - bar_margin * 2
            
            painter.setBrush(QBrush(QColor(60, 60, 60)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_margin, bar_y, bar_width, bar_height, 1, 1)
            
            track_progress = self.track_position / self.track_duration if self.track_duration > 0 else 0
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawRoundedRect(bar_margin, bar_y, int(bar_width * track_progress), bar_height, 1, 1)
            
            painter.setOpacity(1.0)
        
        if progress > 0.5:
            alpha = int(255 * (progress - 0.5) * 2)
            self.draw_expanded_elements(painter, alpha)
    
    def draw_expanded_elements(self, painter, alpha):
        w, h = self.width(), self.height()
        margin = 15
        
        text_x = margin + 70
        bar_width, bar_gap, num_bars = 4, 3, 6
        total_eq_width = num_bars * bar_width + (num_bars - 1) * bar_gap
        eq_x = w - margin - total_eq_width
        text_width = eq_x - text_x - 10
        
        top_offset = 22
        
        title = self.track_title if self.track_title else "Unknown"
        artist = self.track_artist if self.track_artist else "Unknown"
        old_title = self.old_title if self.old_title else "Unknown"
        old_artist = self.old_artist if self.old_artist else "Unknown"
        
        if self.text_animating:
            t = self.text_anim_progress
            style = self.text_animation_style
            
            if style == 0:
                old_offset = -20 * t
                old_alpha = int(alpha * (1 - t))
                new_offset = 20 * (1 - t)
                new_alpha = int(alpha * t)
                self._draw_text_slide(painter, text_x, top_offset, text_width, old_title, old_artist, title, artist, old_offset, new_offset, old_alpha, new_alpha, alpha)
            
            elif style == 1:
                old_alpha = int(alpha * (1 - t))
                new_alpha = int(alpha * t)
                self._draw_text_fade(painter, text_x, top_offset, text_width, old_title, old_artist, title, artist, old_alpha, new_alpha, alpha)
            
            elif style == 2:
                chars_to_show = int(len(title) * t)
                visible_title = title[:chars_to_show]
                chars_artist = int(len(artist) * max(0, t - 0.3) / 0.7) if t > 0.3 else 0
                visible_artist = artist[:chars_artist]
                self._draw_text_typewriter(painter, text_x, top_offset, text_width, visible_title, visible_artist, alpha)
            
            elif style == 3:
                self._draw_text_wave(painter, text_x, top_offset, text_width, title, artist, t, alpha)
            
            elif style == 4:
                scale = 0.8 + 0.2 * t
                blur_alpha = int(alpha * t)
                self._draw_text_blur(painter, text_x, top_offset, text_width, title, artist, scale, blur_alpha, alpha)
        else:
            self._draw_scrolling_text(painter, text_x, top_offset, text_width, title, artist, alpha)
        
        if alpha > 200:
            self.draw_slider_and_controls(painter)
    
    def _draw_text_slide(self, painter, text_x, top_offset, text_width, old_title, old_artist, title, artist, old_offset, new_offset, old_alpha, new_alpha, alpha):
        if old_alpha > 0:
            painter.setPen(QPen(QColor(255, 255, 255, old_alpha)))
            font = QFont("SF Pro Display", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, int(top_offset + old_offset), text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, old_title)
        
        if new_alpha > 0:
            painter.setPen(QPen(QColor(255, 255, 255, new_alpha)))
            font = QFont("SF Pro Display", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, int(top_offset + new_offset), text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
        
        if old_alpha > 0:
            painter.setPen(QPen(QColor(180, 180, 180, old_alpha)))
            font = QFont("SF Pro Display", 10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, int(top_offset + 25 + old_offset), text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, old_artist)
        
        if new_alpha > 0:
            painter.setPen(QPen(QColor(180, 180, 180, new_alpha)))
            font = QFont("SF Pro Display", 10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, int(top_offset + 25 + new_offset), text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
    
    def _draw_text_fade(self, painter, text_x, top_offset, text_width, old_title, old_artist, title, artist, old_alpha, new_alpha, alpha):
        if old_alpha > 0:
            painter.setPen(QPen(QColor(255, 255, 255, old_alpha)))
            font = QFont("SF Pro Display", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, top_offset, text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, old_title)
            
            painter.setPen(QPen(QColor(180, 180, 180, old_alpha)))
            font = QFont("SF Pro Display", 10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, top_offset + 25, text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, old_artist)
        
        if new_alpha > 0:
            painter.setPen(QPen(QColor(255, 255, 255, new_alpha)))
            font = QFont("SF Pro Display", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, top_offset, text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
            
            painter.setPen(QPen(QColor(180, 180, 180, new_alpha)))
            font = QFont("SF Pro Display", 10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(text_x, top_offset + 25, text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
    
    def _draw_text_typewriter(self, painter, text_x, top_offset, text_width, title, artist, alpha):
        painter.setPen(QPen(QColor(255, 255, 255, alpha)))
        font = QFont("SF Pro Display", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_x, top_offset, text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
        
        painter.setPen(QPen(QColor(180, 180, 180, alpha)))
        font = QFont("SF Pro Display", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_x, top_offset + 25, text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
    
    def _draw_text_wave(self, painter, text_x, top_offset, text_width, title, artist, t, alpha):
        font = QFont("SF Pro Display", 12)
        font.setBold(True)
        painter.setFont(font)
        
        x_pos = text_x
        for i, char in enumerate(title):
            wave_offset = math.sin((t * 4 - i * 0.3)) * 5 * (1 - t)
            char_alpha = int(alpha * min(1.0, max(0, (t * len(title) - i) / 3)))
            if char_alpha > 0:
                painter.setPen(QPen(QColor(255, 255, 255, char_alpha)))
                painter.drawText(int(x_pos), int(top_offset + wave_offset), 200, 25, Qt.AlignLeft | Qt.AlignVCenter, char)
            x_pos += painter.fontMetrics().horizontalAdvance(char)
        
        font = QFont("SF Pro Display", 10)
        font.setBold(True)
        painter.setFont(font)
        
        x_pos = text_x
        for i, char in enumerate(artist):
            wave_offset = math.sin((t * 4 - i * 0.3 - 1)) * 5 * (1 - t)
            char_alpha = int(alpha * min(1.0, max(0, ((t - 0.2) * len(artist) - i) / 3))) if t > 0.2 else 0
            if char_alpha > 0:
                painter.setPen(QPen(QColor(180, 180, 180, char_alpha)))
                painter.drawText(int(x_pos), int(top_offset + 25 + wave_offset), 200, 20, Qt.AlignLeft | Qt.AlignVCenter, char)
            x_pos += painter.fontMetrics().horizontalAdvance(char)
    
    def _draw_text_blur(self, painter, text_x, top_offset, text_width, title, artist, scale, blur_alpha, alpha):
        painter.save()
        
        center_x = text_x + text_width / 2
        center_y = top_offset + 12
        
        painter.translate(center_x, center_y)
        painter.scale(scale, scale)
        painter.translate(-center_x, -center_y)
        
        painter.setPen(QPen(QColor(255, 255, 255, blur_alpha)))
        font = QFont("SF Pro Display", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_x, top_offset, text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
        
        painter.restore()
        painter.save()
        
        center_y = top_offset + 35
        painter.translate(center_x, center_y)
        painter.scale(scale, scale)
        painter.translate(-center_x, -center_y)
        
        painter.setPen(QPen(QColor(180, 180, 180, blur_alpha)))
        font = QFont("SF Pro Display", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_x, top_offset + 25, text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
        
        painter.restore()
    
    def _draw_scrolling_text(self, painter, text_x, top_offset, text_width, title, artist, alpha):
        font_title = QFont("SF Pro Display", 12)
        font_title.setBold(True)
        painter.setFont(font_title)
        title_text_width = painter.fontMetrics().horizontalAdvance(title)
        self._title_text_width = title_text_width
        
        font_artist = QFont("SF Pro Display", 10)
        font_artist.setBold(True)
        
        painter.save()
        painter.setClipRect(text_x, top_offset, text_width, 50)
        
        painter.setFont(font_title)
        painter.setPen(QPen(QColor(255, 255, 255, alpha)))
        
        gap = 60
        
        if title_text_width > text_width:
            self.title_needs_scroll = True
            scroll_x = text_x - self.title_scroll_offset
            painter.drawText(int(scroll_x), top_offset, title_text_width + gap, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
            painter.drawText(int(scroll_x + title_text_width + gap), top_offset, title_text_width + gap, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
        else:
            self.title_needs_scroll = False
            painter.drawText(text_x, top_offset, text_width, 25, Qt.AlignLeft | Qt.AlignVCenter, title)
        
        painter.setFont(font_artist)
        artist_text_width = painter.fontMetrics().horizontalAdvance(artist)
        self._artist_text_width = artist_text_width
        painter.setPen(QPen(QColor(180, 180, 180, alpha)))
        
        if artist_text_width > text_width:
            self.artist_needs_scroll = True
            scroll_x = text_x - self.artist_scroll_offset
            painter.drawText(int(scroll_x), top_offset + 25, artist_text_width + gap, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
            painter.drawText(int(scroll_x + artist_text_width + gap), top_offset + 25, artist_text_width + gap, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
        else:
            self.artist_needs_scroll = False
            painter.drawText(text_x, top_offset + 25, text_width, 20, Qt.AlignLeft | Qt.AlignVCenter, artist)
        
        painter.restore()
    
    def draw_slider_and_controls(self, painter):
        w, h = self.width(), self.height()
        margin = 15
        
        slider_y = 105
        slider_margin = 50
        slider_width = w - slider_margin * 2
        slider_height = 6
        
        painter.setPen(QPen(QColor(150, 150, 150)))
        font = QFont("SF Pro Display", 10)
        font.setBold(True)
        painter.setFont(font)
        pos_str = self.format_time(self.track_position)
        painter.drawText(margin - 15, slider_y - 8, 45, 20, Qt.AlignRight | Qt.AlignVCenter, pos_str)
        
        if self.show_time_remaining:
            remaining = self.track_duration - self.track_position
            rem_str = "-" + self.format_time(remaining) if remaining > 0 else "0:00"
        else:
            rem_str = self.format_time(self.track_duration)
        painter.drawText(w - margin - 31, slider_y - 8, 45, 20, Qt.AlignLeft | Qt.AlignVCenter, rem_str)
        
        progress_x = slider_margin
        progress_width = slider_width
        progress = self.track_position / self.track_duration if self.track_duration > 0 else 0
        
        self.slider_rect = (progress_x, slider_y - 6, progress_width, 18)
        
        painter.setBrush(QBrush(QColor(60, 60, 60)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(progress_x, slider_y, progress_width, slider_height, 3, 3)
        
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(progress_x, slider_y, int(progress_width * progress), slider_height, 3, 3)
        
        btn_y = 130
        btn_size = 48
        btn_gap = 15
        center_x = w // 2
        
        self.draw_prev_button(painter, center_x - btn_size - btn_gap - btn_size // 2, btn_y, btn_size)
        self.draw_play_button(painter, center_x - btn_size // 2, btn_y, btn_size)
        self.draw_next_button(painter, center_x + btn_size // 2 + btn_gap, btn_y, btn_size)

    def draw_prev_button(self, painter, x, y, size):
        center_x = x + size / 2
        center_y = y + size / 2
        scaled_size = int(size * self.prev_scale)
        draw_x = int(center_x - scaled_size / 2 - self.prev_offset)
        draw_y = int(center_y - scaled_size / 2)
        if scaled_size > 1:
            scaled = self.icon_prev.scaled(scaled_size, scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(draw_x, draw_y, scaled)

    def draw_next_button(self, painter, x, y, size):
        center_x = x + size / 2
        center_y = y + size / 2
        scaled_size = int(size * self.next_scale)
        draw_x = int(center_x - scaled_size / 2 + self.next_offset)
        draw_y = int(center_y - scaled_size / 2)
        if scaled_size > 1:
            scaled = self.icon_next.scaled(scaled_size, scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(draw_x, draw_y, scaled)
    
    def start_prev_animation(self):
        self.prev_animating = True
        self.prev_phase = 0
        self.prev_scale = 1.0
        self.prev_offset = 0.0
    
    def start_next_animation(self):
        self.next_animating = True
        self.next_phase = 0
        self.next_scale = 1.0
        self.next_offset = 0.0
    
    def update_arrow_animations(self):
        if self.prev_animating:
            if self.prev_phase == 0:
                self.prev_scale *= 0.7
                self.prev_offset += 3
                if self.prev_scale <= 0.1:
                    self.prev_phase = 1
                    self.prev_scale = 0.1
                    self.prev_offset = -15
            else:
                self.prev_scale += (1.0 - self.prev_scale) * 0.4
                self.prev_offset += (0 - self.prev_offset) * 0.4
                if self.prev_scale >= 0.95 and abs(self.prev_offset) < 1:
                    self.prev_scale = 1.0
                    self.prev_offset = 0.0
                    self.prev_animating = False
        
        if self.next_animating:
            if self.next_phase == 0:
                self.next_scale *= 0.7
                self.next_offset += 3
                if self.next_scale <= 0.1:
                    self.next_phase = 1
                    self.next_scale = 0.1
                    self.next_offset = -15
            else:
                self.next_scale += (1.0 - self.next_scale) * 0.4
                self.next_offset += (0 - self.next_offset) * 0.4
                if self.next_scale >= 0.95 and abs(self.next_offset) < 1:
                    self.next_scale = 1.0
                    self.next_offset = 0.0
                    self.next_animating = False

    def draw_play_button(self, painter, x, y, size):
        center_x = x + size / 2
        center_y = y + size / 2
        
        scale = self.play_pause_scale
        scaled_size = int(size * scale)
        
        if self.play_pause_animating:
            if self.play_pause_shrinking:
                icon = self.icon_play if self.play_pause_target_playing else self.icon_pause
                is_pause = not self.play_pause_target_playing
            else:
                icon = self.icon_pause if self.play_pause_target_playing else self.icon_play
                is_pause = self.play_pause_target_playing
        else:
            icon = self.icon_pause if self.is_media_playing else self.icon_play
            is_pause = self.is_media_playing
        
        offset_x = 8 if is_pause else 2
        draw_x = int(center_x - scaled_size / 2) + offset_x
        draw_y = int(center_y - scaled_size / 2)
        
        if scaled_size > 1:
            scaled = icon.scaled(scaled_size, scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(draw_x, draw_y, scaled)
    
    def start_play_pause_animation(self, target_playing):
        self.play_pause_target_playing = target_playing
        self.play_pause_animating = True
        self.play_pause_shrinking = True
        self.play_pause_scale = 1.0
    
    def update_play_pause_animation(self):
        if not self.play_pause_animating:
            return
        
        if self.play_pause_shrinking:
            self.play_pause_scale *= 0.5
            if self.play_pause_scale <= 0.05:
                self.play_pause_scale = 0
                self.play_pause_shrinking = False
        else:
            self.play_pause_scale += (1.0 - self.play_pause_scale) * 0.5
            if self.play_pause_scale >= 0.95:
                self.play_pause_scale = 1.0
                self.play_pause_animating = False

    def format_time(self, seconds):
        if seconds < 0:
            seconds = 0
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins}:{secs:02d}"

    def lerp_color(self, c1, c2, t):
        return QColor(int(c1.red() + (c2.red() - c1.red()) * t), int(c1.green() + (c2.green() - c1.green()) * t), int(c1.blue() + (c2.blue() - c1.blue()) * t))

    def update_equalizer(self):
        target_pause = 0.0 if self.is_media_playing else 1.0
        self.pause_progress += (target_pause - self.pause_progress) * 0.15
        
        self.corner_radius_current += (self.corner_radius_target - self.corner_radius_current) * 0.15
        self.compact_corner_radius_current += (self.compact_corner_radius_target - self.compact_corner_radius_current) * 0.15
        
        if self.is_media_playing:
            bands = self.audio_analyzer.get_bands()
            sensitivity = self.eq_sensitivity / 100.0
            for i in range(min(len(bands), len(self.eq_bars))):
                adjusted_band = bands[i] * sensitivity
                self.eq_bars[i] += (adjusted_band - self.eq_bars[i]) * 0.4
                self.eq_bars[i] = max(0.1, min(1.0, self.eq_bars[i]))
            if self.eq_color_from_art:
                self.eq_color_top = self.lerp_color(self.eq_color_top, self.eq_color_top_target, 0.1)
                self.eq_color_bottom = self.lerp_color(self.eq_color_bottom, self.eq_color_bottom_target, 0.1)
            else:
                self.eq_color_top = QColor(255, 255, 255)
                self.eq_color_bottom = QColor(255, 255, 255)
        
        self.update_play_pause_animation()
        self.update_arrow_animations()
        
        if self.text_animating:
            self.text_anim_progress += 0.08
            if self.text_anim_progress >= 1.0:
                self.text_anim_progress = 1.0
                self.text_animating = False
        
        if self.is_expanded and not self.text_animating:
            current_time = time.time()
            scroll_speed = 30.0
            pause_duration = 2.5
            gap = 60
            
            if self.title_needs_scroll:
                if not self.title_scrolling:
                    if self.scroll_pause_start == 0:
                        self.scroll_pause_start = current_time
                    if current_time - self.scroll_pause_start >= pause_duration:
                        self.title_scrolling = True
                        self.scroll_start_time = current_time
                else:
                    elapsed = current_time - self.scroll_start_time
                    title_width = self._title_text_width if self._title_text_width > 0 else 200
                    max_scroll = title_width + gap
                    self.title_scroll_offset = (elapsed * scroll_speed) % max_scroll
            else:
                self.title_scroll_offset = 0
                self.title_scrolling = False
                self.scroll_pause_start = 0
            
            if self.artist_needs_scroll:
                if not self.artist_scrolling:
                    self.artist_scrolling = True
                    self.artist_scroll_start = current_time
                elapsed = current_time - getattr(self, 'artist_scroll_start', current_time)
                artist_width = self._artist_text_width if self._artist_text_width > 0 else 150
                max_scroll = artist_width + gap
                self.artist_scroll_offset = (elapsed * scroll_speed) % max_scroll
            else:
                self.artist_scroll_offset = 0
                self.artist_scrolling = False
        else:
            self.title_scroll_offset = 0
            self.artist_scroll_offset = 0
            self.title_scrolling = False
            self.artist_scrolling = False
            self.scroll_pause_start = 0
        
        if self.has_media_session or self.is_media_playing:
            self.update()

    def update_flip(self):
        if not self.flip_animating:
            return
        self.flip_angle += 12
        if self.flip_angle >= 90 and self.new_album_art is not None:
            self.album_art = self.new_album_art
            if self.new_eq_colors:
                self.eq_color_top_target, self.eq_color_bottom_target = self.new_eq_colors
            self.new_album_art = None
            self.new_eq_colors = None
        if self.flip_angle >= 180:
            self.flip_angle = 0
            self.flip_animating = False
        self.update()

    def start_flip_animation(self, new_art, new_colors):
        self.new_album_art = new_art
        self.new_eq_colors = new_colors
        self.flip_angle = 0
        self.flip_animating = True

    def get_current_width(self):
        return self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width

    def check_media(self):
        if self.checking_media:
            return
        self.checking_media = True
        threading.Thread(target=self._check_media_thread, daemon=True).start()

    def _check_media_thread(self):
        async def get_media_info():
            try:
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                if session:
                    info = session.get_playback_info()
                    is_playing = info.playback_status == PlaybackStatus.PLAYING
                    thumbnail = None
                    title = ""
                    artist = ""
                    position = 0.0
                    duration = 0.0
                    
                    try:
                        timeline = session.get_timeline_properties()
                        if timeline:
                            position = timeline.position.total_seconds()
                            duration = timeline.end_time.total_seconds()
                    except:
                        pass
                    
                    try:
                        media_props = await session.try_get_media_properties_async()
                        if media_props:
                            title = media_props.title or ""
                            artist = media_props.artist or ""
                            if title != self.track_title and media_props.thumbnail:
                                try:
                                    stream = await media_props.thumbnail.open_read_async()
                                    size = stream.size
                                    buffer = Buffer(size)
                                    await stream.read_async(buffer, size, InputStreamOptions.READ_AHEAD)
                                    reader = DataReader.from_buffer(buffer)
                                    thumbnail = bytes([reader.read_byte() for _ in range(size)])
                                except:
                                    pass
                    except:
                        pass
                    return is_playing, thumbnail, title, artist, position, duration
            except:
                pass
            return False, None, "", "", 0.0, 0.0
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(get_media_info())
            loop.close()
        except:
            result = (False, None, "", "", 0.0, 0.0)
        self.media_updated.emit(*result)

    def extract_colors_from_image(self, img):
        if img.isNull():
            return QColor(255, 255, 255), QColor(255, 255, 255)
        scaled = img.scaled(1, 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        top_color = QColor(scaled.pixel(0, 0))
        bottom_color = QColor(scaled.pixel(0, 1))
        def brighten(c):
            r, g, b = c.red(), c.green(), c.blue()
            if (r + g + b) / 3 < 80:
                return QColor(min(255, int(r * 2 + 50)), min(255, int(g * 2 + 50)), min(255, int(b * 2 + 50)))
            return c
        return brighten(top_color), brighten(bottom_color)

    def on_media_updated(self, is_playing, thumbnail, title, artist, position, duration):
        self.checking_media = False
        
        if title != self.track_title and title and self.text_animation_enabled:
            self.old_title = self.track_title
            self.old_artist = self.track_artist
            self.text_anim_progress = 0.0
            self.text_animating = True
        
        self.track_title = title
        self.track_artist = artist
        self.track_duration = duration
        
        if not self.dragging_slider:
            self.track_position = position
        
        has_session = thumbnail is not None or title or artist or duration > 0
        
        if thumbnail:
            thumb_hash = hash(thumbnail)
            if thumb_hash != self.last_thumbnail_hash:
                self.last_thumbnail_hash = thumb_hash
                img = QImage()
                img.loadFromData(thumbnail)
                new_art = QPixmap.fromImage(img)
                new_colors = self.extract_colors_from_image(img)
                if self.album_art and self.is_media_playing and not self.flip_animating and self.flip_animation_enabled:
                    self.start_flip_animation(new_art, new_colors)
                else:
                    self.album_art = new_art
                    self.eq_color_top_target, self.eq_color_bottom_target = new_colors
        elif not has_session:
            self.album_art = None
            self.last_thumbnail_hash = None
            self.eq_color_top_target = QColor(255, 255, 255)
            self.eq_color_bottom_target = QColor(255, 255, 255)
        
        session_changed = has_session != self.has_media_session
        playing_changed = is_playing != self.is_media_playing
        self.has_media_session = has_session
        
        if playing_changed or session_changed:
            self.is_media_playing = is_playing
            if not self.is_expanded:
                if has_session:
                    if self.is_hidden and self.autohide:
                        self.show_island()
                    else:
                        self.animate_to(self.media_width, self.base_height)
                else:
                    if self.autohide and not self.is_hidden:
                        self.hide_island()
                    else:
                        self.animate_to(self.base_width, self.base_height)
            if is_playing:
                self.audio_analyzer.start()
            else:
                self.audio_analyzer.stop()
        if is_playing and not self.audio_analyzer.running:
            self.audio_analyzer.start()
        self.update()

    def get_current_screen(self):
        screens = QApplication.screens()
        if self.monitor_index < len(screens):
            return screens[self.monitor_index]
        return QApplication.primaryScreen()
    
    def animate_to(self, width, height, expanded=False):
        screen = self.get_current_screen().geometry()
        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + self.top_offset
        self.now_width = width
        self.now_height = height
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(x, y, width, height))
        self.animation.start()

    def on_animation_finished(self):
        pass

    def toggle_expanded(self):
        if self.is_expanded:
            self.is_expanded = False
            self.slider_rect = None
            target_w = self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width
            self.animate_to(target_w, self.base_height, expanded=False)
        else:
            if self.has_media_session:
                self.is_expanded = True
                self.animate_to(self.expanded_width, self.expanded_height, expanded=True)
                self.activateWindow()
                self.setFocus()
    
    def hide_island(self):
        self.is_hidden = True
        screen = self.get_current_screen().geometry()
        target_w = self.media_width if self.is_media_playing else self.base_width
        x = screen.x() + (screen.width() - target_w) // 2
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(QRect(x, screen.y() - self.base_height - 10, target_w, self.base_height))
        self.animation.start()
    
    def show_island(self):
        if not self.is_hidden:
            return
        self.is_hidden = False
        target_w = self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width
        self.animate_to(target_w, self.base_height, expanded=False)

    def send_media_command(self, command):
        threading.Thread(target=self._send_command_thread, args=(command,), daemon=True).start()

    def _send_command_thread(self, command):
        async def send():
            try:
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                if session:
                    if command == "play_pause":
                        await session.try_toggle_play_pause_async()
                    elif command == "next":
                        await session.try_skip_next_async()
                    elif command == "prev":
                        await session.try_skip_previous_async()
            except:
                pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send())
        loop.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_expanded:
                pos = event.pos()
                w, h = self.width(), self.height()
                btn_y = 130
                btn_size = 48
                center_x = w // 2
                
                if self.slider_rect:
                    sx, sy, sw, sh = self.slider_rect
                    if sx <= pos.x() <= sx + sw and sy <= pos.y() <= sy + sh:
                        self.dragging_slider = True
                        self.update_slider_position(pos.x())
                        return
                
                btn_gap = 15
                prev_x = center_x - btn_size - btn_gap - btn_size // 2
                play_x = center_x - btn_size // 2
                next_x = center_x + btn_size // 2 + btn_gap
                
                if btn_y <= pos.y() <= btn_y + btn_size:
                    if prev_x <= pos.x() <= prev_x + btn_size:
                        if self.button_animation_enabled:
                            self.start_prev_animation()
                        self.send_media_command("prev")
                        return
                    elif play_x <= pos.x() <= play_x + btn_size:
                        if self.button_animation_enabled:
                            self.start_play_pause_animation(not self.is_media_playing)
                        self.send_media_command("play_pause")
                        return
                    elif next_x <= pos.x() <= next_x + btn_size:
                        if self.button_animation_enabled:
                            self.start_next_animation()
                        self.send_media_command("next")
                        return
                self.toggle_expanded()
            else:
                self.is_pressing = True
                base = self.get_current_width()
                self.animate_to(base + 15, self.base_height + 5)
                self.press_timer = QTimer()
                self.press_timer.setSingleShot(True)
                self.press_timer.timeout.connect(self.on_long_press)
                self.press_timer.start(self.long_press_duration)
        elif event.button() == Qt.RightButton:
            if self.is_expanded:
                self.toggle_expanded()
            elif not self.is_hidden:
                self.hide_island()
        event.accept()
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_expanded:
            self._pending_open_app = False
            
            action = self.double_click_action
            if action == 0:
                pass
            elif action == 1:
                if self.has_media_session:
                    self.toggle_expanded()
            elif action == 2:
                self.send_media_command("play_pause")
            elif action == 3:
                self.send_media_command("next")
        event.accept()
    
    def enterEvent(self, event):
        if self.is_hidden:
            self.show_island()
        event.accept()
    
    def leaveEvent(self, event):
        event.accept()
    
    def mouseMoveEvent(self, event):
        if self.dragging_slider and self.slider_rect:
            self.update_slider_position(event.pos().x())
        event.accept()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.dragging_slider:
                self.dragging_slider = False
            if self.press_timer and self.press_timer.isActive():
                self.press_timer.stop()
                if self.has_media_session and self.click_to_open_app and not self.is_expanded:
                    self._pending_open_app = True
                    QTimer.singleShot(250, self._check_open_app)
            if self.is_pressing and not self.is_expanded:
                self.is_pressing = False
                target_w = self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width
                self.animate_to(target_w, self.base_height)
        event.accept()
    
    def _check_open_app(self):
        if getattr(self, '_pending_open_app', False):
            self._pending_open_app = False
            self.open_media_app()
    
    def open_media_app(self):
        threading.Thread(target=self._open_media_app_thread, daemon=True).start()
    
    def _open_media_app_thread(self):
        async def activate():
            try:
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                if session:
                    source_app_id = session.source_app_user_model_id
                    if source_app_id:
                        app_name = source_app_id.replace('.exe', '').split('\\')[-1].split('!')[-1].lower()
                        self._activate_window_by_name(app_name)
            except:
                pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(activate())
        loop.close()
    
    def _activate_window_by_name(self, app_name):
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        OpenProcess = kernel32.OpenProcess
        GetModuleBaseNameW = psapi.GetModuleBaseNameW
        CloseHandle = kernel32.CloseHandle
        IsWindowVisible = user32.IsWindowVisible
        
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        
        found_hwnd = [None]
        
        def enum_callback(hwnd, lparam):
            if not IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value)
            if handle:
                buf = ctypes.create_unicode_buffer(260)
                GetModuleBaseNameW(handle, None, buf, 260)
                CloseHandle(handle)
                proc_name = buf.value.lower().replace('.exe', '')
                if app_name in proc_name or proc_name in app_name:
                    found_hwnd[0] = hwnd
                    return False
            return True
        
        EnumWindows(EnumWindowsProc(enum_callback), 0)
        
        if found_hwnd[0]:
            user32.ShowWindow(found_hwnd[0], 9)
            user32.SetForegroundWindow(found_hwnd[0])
    
    def update_slider_position(self, x):
        if not self.slider_rect or self.track_duration <= 0:
            return
        sx, sy, sw, sh = self.slider_rect
        progress = max(0, min(1, (x - sx) / sw))
        new_position = progress * self.track_duration
        self.track_position = new_position
        self.seek_to_position(new_position)
        self.update()
    
    def seek_to_position(self, position):
        threading.Thread(target=self._seek_thread, args=(position,), daemon=True).start()
    
    def _seek_thread(self, position):
        async def seek():
            try:
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                if session:
                    from datetime import timedelta
                    await session.try_change_playback_position_async(int(position * 10000000))
            except:
                pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(seek())
        loop.close()
    
    def on_long_press(self):
        self.is_pressing = False
        if not self.is_expanded and self.has_media_session:
            self.toggle_expanded()
        else:
            target_w = self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width
            self.animate_to(target_w, self.base_height)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.is_expanded:
                self.toggle_expanded()
        event.accept()
    
    def focusOutEvent(self, event):
        if self.is_expanded:
            self.toggle_expanded()
        event.accept()
    
    def showEvent(self, event):
        self.setFocus()
        event.accept()

    def closeEvent(self, event):
        self.audio_analyzer.stop()
        event.accept()
    
    def apply_settings(self, config):
        self.config = config
        self.top_offset = config.get('top_offset', 15)
        self.show_equalizer = config.get('show_equalizer', True)
        self.eq_color_from_art = config.get('eq_color_from_art', True)
        self.text_animation_enabled = config.get('text_animation', True)
        self.text_animation_style = config.get('text_animation_style', 0)
        self.button_animation_enabled = config.get('button_animation', True)
        self.flip_animation_enabled = config.get('flip_animation', True)
        self.bounce_enabled = config.get('bounce_effect', True)
        self.animation_speed = config.get('animation_speed', 100) / 100.0
        self.corner_radius = config.get('corner_radius', 20)
        self.corner_radius_target = self.corner_radius
        self.compact_corner_radius = config.get('compact_corner_radius', 20)
        self.compact_corner_radius_target = self.compact_corner_radius
        self.click_to_open_app = config.get('click_to_open_app', True)
        self.long_press_duration = config.get('long_press_duration', 250)
        self.show_time_remaining = config.get('show_time_remaining', True)
        self.eq_bar_count = config.get('eq_bar_count', 6)
        self.eq_sensitivity = config.get('eq_sensitivity', 100)
        self.double_click_action = config.get('double_click_action', 0)
        self.show_progress_bar = config.get('show_progress_bar', True)
        self.autohide = config.get('autohide', False)
        self.monitor_index = config.get('monitor', 0)
        
        if self.autohide and not self.has_media_session and not self.is_hidden:
            self.hide_island()
        elif not self.autohide and self.is_hidden:
            self.show_island()
        
        scale = config.get('size_scale', 100) / 100.0
        idle_width = config.get('idle_width', 150)
        media_width = config.get('media_width', 200)
        self.base_width = int(idle_width * scale)
        self.base_height = int(40 * scale)
        self.expanded_width = 330
        self.expanded_height = 200
        self.media_width = int(media_width * scale)
        
        opacity = config.get('opacity', 100) / 100.0
        self.setWindowOpacity(opacity)
        
        base_duration = 350
        self.animation.setDuration(int(base_duration / self.animation_speed))
        if self.bounce_enabled:
            self.animation.setEasingCurve(QEasingCurve.OutBack)
        else:
            self.animation.setEasingCurve(QEasingCurve.OutCubic)
        
        if not self.is_expanded:
            target_w = self.media_width if (self.is_media_playing or self.has_media_session) else self.base_width
            self.animate_to(target_w, self.base_height)


class HoverZone(QWidget):
    def __init__(self, island):
        super().__init__()
        self.island = island
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        screen = QApplication.primaryScreen().geometry()
        zone_width = 400
        zone_x = (screen.width() - zone_width) // 2
        self.setGeometry(zone_x, 0, zone_width, 15)
    
    def enterEvent(self, event):
        if self.island.is_hidden:
            self.island.show_island()
        event.accept()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setBrush(QBrush(QColor(0, 0, 0, 1)))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())


CONFIG_DIR = os.path.join(os.environ.get('APPDATA', ''), 'WindowsIsland')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

DEFAULT_CONFIG = {
    'language': 'en',
    'autostart': True,
    'topmost': True,
    'autohide': False,
    'top_offset': 15,
    'monitor': 0,
    'size_scale': 100,
    'opacity': 100,
    'corner_radius': 20,
    'show_equalizer': True,
    'eq_color_from_art': True,
    'eq_bar_count': 6,
    'animation_speed': 100,
    'bounce_effect': True,
    'text_animation': True,
    'text_animation_style': 3,
    'button_animation': True,
    'flip_animation': True,
    'click_to_open_app': True,
    'long_press_duration': 250,
    'show_time_remaining': True,
    'compact_corner_radius': 20,
    'double_click_action': 2,
    'show_progress_bar': False,
    'idle_width': 150,
    'media_width': 200,
    'eq_sensitivity': 100
}

TRANSLATIONS = {
    'ru': {
        'title': 'Windows Island',
        'subtitle': 'Настройки виджета',
        'tab_general': 'Основные',
        'tab_appearance': 'Внешний вид',
        'tab_animation': 'Анимации',
        'tab_about': 'О программе',
        'language': 'Язык:',
        'autostart': 'Запускать при старте Windows',
        'topmost': 'Всегда поверх других окон',
        'autohide': 'Скрывать при отсутствии медиа',
        'top_offset': 'Отступ от верха:',
        'monitor': 'Монитор:',
        'monitor_primary': 'Основной',
        'size': 'Размер острова (compact):',
        'opacity': 'Прозрачность:',
        'corner_radius': 'Закругление углов:',
        'show_eq': 'Показывать эквалайзер',
        'eq_color': 'Цвет эквалайзера из обложки',
        'anim_speed': 'Скорость анимаций:',
        'bounce': 'Эффект отскока при открытии',
        'text_anim': 'Анимация смены трека',
        'text_anim_style': 'Стиль анимации текста:',
        'text_anim_slide': 'Скольжение',
        'text_anim_fade': 'Затухание',
        'text_anim_typewriter': 'Печатная машинка',
        'text_anim_wave': 'Волна',
        'text_anim_blur': 'Размытие',
        'btn_anim': 'Анимация кнопок управления',
        'flip_anim': '3D переворот обложки',
        'click_open_app': 'Клик открывает приложение',
        'long_press': 'Длительность зажатия (мс):',
        'show_remaining': 'Показывать оставшееся время',
        'eq_bars': 'Полосок эквалайзера:',
        'compact_radius': 'Закругление (compact):',
        'double_click': 'Двойной клик:',
        'dc_none': 'Ничего',
        'dc_expand': 'Развернуть',
        'dc_playpause': 'Play/Pause',
        'dc_next': 'Следующий трек',
        'show_progress': 'Прогресс в compact режиме',
        'idle_width': 'Ширина (без медиа):',
        'media_width': 'Ширина (с медиа):',
        'eq_sensitivity': 'Чувствительность эквалайзера:',
        'version': 'Версия',
        'description': 'Виджет в стиле Dynamic Island от Apple\nдля Windows с управлением медиа',
        'author': 'Создано dmavv за пару часов вайбкодинга ✨',
        'reset': 'Сбросить всё',
        'save': 'Сохранить',
        'show_island': 'Показать остров',
        'settings': 'Настройки',
        'quit': 'Выход'
    },
    'en': {
        'title': 'Windows Island',
        'subtitle': 'Widget Settings',
        'tab_general': 'General',
        'tab_appearance': 'Appearance',
        'tab_animation': 'Animations',
        'tab_about': 'About',
        'language': 'Language:',
        'autostart': 'Start with Windows',
        'topmost': 'Always on top',
        'autohide': 'Hide when no media',
        'top_offset': 'Top offset:',
        'monitor': 'Monitor:',
        'monitor_primary': 'Primary',
        'size': 'Island size (compact):',
        'opacity': 'Opacity:',
        'corner_radius': 'Corner radius:',
        'show_eq': 'Show equalizer',
        'eq_color': 'Equalizer color from artwork',
        'anim_speed': 'Animation speed:',
        'bounce': 'Bounce effect on open',
        'text_anim': 'Track change animation',
        'text_anim_style': 'Text animation style:',
        'text_anim_slide': 'Slide',
        'text_anim_fade': 'Fade',
        'text_anim_typewriter': 'Typewriter',
        'text_anim_wave': 'Wave',
        'text_anim_blur': 'Blur',
        'btn_anim': 'Button animations',
        'flip_anim': '3D cover flip',
        'click_open_app': 'Click opens app',
        'long_press': 'Long press duration (ms):',
        'show_remaining': 'Show remaining time',
        'eq_bars': 'Equalizer bars:',
        'compact_radius': 'Corner radius (compact):',
        'double_click': 'Double click:',
        'dc_none': 'Nothing',
        'dc_expand': 'Expand',
        'dc_playpause': 'Play/Pause',
        'dc_next': 'Next track',
        'show_progress': 'Progress in compact mode',
        'idle_width': 'Width (no media):',
        'media_width': 'Width (with media):',
        'eq_sensitivity': 'Equalizer sensitivity:',
        'version': 'Version',
        'description': 'Dynamic Island style widget for Windows\nwith media controls',
        'author': 'Created by dmavv in a couple hours of vibecoding ✨',
        'reset': 'Reset All',
        'save': 'Save',
        'show_island': 'Show Island',
        'settings': 'Settings',
        'quit': 'Quit'
    }
}


def load_config():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def set_autostart(enabled):
    import subprocess
    task_name = "WindowsIsland"
    
    try:
        if enabled:
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            
            subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            result = subprocess.run([
                'schtasks', '/create',
                '/tn', task_name,
                '/tr', app_path,
                '/sc', 'onlogon',
                '/rl', 'limited',
                '/f'
            ], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            return result.returncode == 0
        else:
            result = subprocess.run(
                ['schtasks', '/delete', '/tn', task_name, '/f'],
                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            return True
    except Exception as e:
        print(f"Ошибка автозапуска: {e}")
        return False


def is_autostart_enabled():
    import subprocess
    task_name = "WindowsIsland"
    
    try:
        result = subprocess.run(
            ['schtasks', '/query', '/tn', task_name],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.returncode == 0
    except:
        return False


SETTINGS_STYLE = """
QWidget {
    background-color: #1a1a1a;
    color: #ffffff;
    font-family: 'Segoe UI', sans-serif;
}
QTabWidget::pane {
    border: none;
    background-color: #1a1a1a;
}
QTabBar::tab {
    background-color: #2a2a2a;
    color: #888888;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected {
    background-color: #3a3a3a;
    color: #ffffff;
}
QTabBar::tab:hover {
    background-color: #333333;
}
QLabel {
    color: #ffffff;
    font-size: 13px;
}
QLabel#title {
    font-size: 24px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#subtitle {
    font-size: 12px;
    color: #888888;
}
QCheckBox {
    color: #ffffff;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 2px solid #555555;
    background-color: #2a2a2a;
}
QCheckBox::indicator:checked {
    background-color: #007AFF;
    border-color: #007AFF;
}
QCheckBox::indicator:hover {
    border-color: #007AFF;
}
QSlider::groove:horizontal {
    height: 6px;
    background-color: #3a3a3a;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 18px;
    height: 18px;
    margin: -6px 0;
    background-color: #ffffff;
    border-radius: 9px;
}
QSlider::sub-page:horizontal {
    background-color: #007AFF;
    border-radius: 3px;
}
QSpinBox {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 5px 10px;
    color: #ffffff;
    font-size: 13px;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 20px;
    background-color: #3a3a3a;
    border-radius: 3px;
}
QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #ffffff;
    font-size: 13px;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    color: #ffffff;
    selection-background-color: #007AFF;
}
QPushButton {
    background-color: #007AFF;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #0066DD;
}
QPushButton:pressed {
    background-color: #0055CC;
}
QPushButton#secondary {
    background-color: #3a3a3a;
}
QPushButton#secondary:hover {
    background-color: #4a4a4a;
}
QFrame#separator {
    background-color: #3a3a3a;
    max-height: 1px;
}
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    background-color: transparent;
    width: 6px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background-color: #555555;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #777777;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)
        
        self.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 6px;
                margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(128, 128, 128, 0.5);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(160, 160, 160, 0.7);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self._scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_animation.setDuration(300)
        
        QScroller.grabGesture(self.viewport(), QScroller.LeftMouseButtonGesture)
        scroller = QScroller.scroller(self.viewport())
        props = scroller.scrollerProperties()
        props.setScrollMetric(1, 0.3)
        props.setScrollMetric(7, 0.3)
        scroller.setScrollerProperties(props)
    
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        current = self.verticalScrollBar().value()
        
        if self._scroll_animation.state() == QPropertyAnimation.Running:
            current = self._scroll_animation.endValue()
        
        step = 80
        target = current - (delta // 120) * step
        
        target = max(0, min(target, self.verticalScrollBar().maximum()))
        
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(self.verticalScrollBar().value())
        self._scroll_animation.setEndValue(target)
        self._scroll_animation.start()
        
        event.accept()


class SettingsWindow(QWidget):
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, island):
        super().__init__()
        self.island = island
        self.config = load_config()
        self.tr = TRANSLATIONS[self.config['language']]
        
        self.setWindowTitle("Windows Island Settings")
        self.setFixedSize(500, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(SETTINGS_STYLE)
        
        self.dragging = False
        self.drag_pos = QPoint()
        
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(200)
        self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.init_ui()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowOpacity(0)
        self.fade_animation.setStartValue(0)
        self.fade_animation.setEndValue(1)
        self.fade_animation.start()
    
    def hide_with_animation(self):
        self.fade_animation.setStartValue(1)
        self.fade_animation.setEndValue(0)
        self.fade_animation.finished.connect(self._do_hide)
        self.fade_animation.start()
    
    def _do_hide(self):
        self.fade_animation.finished.disconnect(self._do_hide)
        super().hide()
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        container = QFrame()
        container.setStyleSheet("QFrame { background-color: #1a1a1a; border-radius: 16px; }")
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setContentsMargins(20, 20, 20, 20)
        self.container_layout.setSpacing(15)
        
        header = QHBoxLayout()
        self.title_label = QLabel(self.tr['title'])
        self.title_label.setObjectName("title")
        header.addWidget(self.title_label)
        header.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                font-size: 14px;
                padding: 0;
                color: #888888;
            }
            QPushButton:hover { 
                color: #ffffff;
            }
        """)
        close_btn.clicked.connect(self.hide_with_animation)
        header.addWidget(close_btn)
        self.container_layout.addLayout(header)
        
        self.subtitle_label = QLabel(self.tr['subtitle'])
        self.subtitle_label.setObjectName("subtitle")
        self.container_layout.addWidget(self.subtitle_label)
        
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        self.container_layout.addWidget(sep)
        
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_general_tab(), self.tr['tab_general'])
        self.tabs.addTab(self.create_appearance_tab(), self.tr['tab_appearance'])
        self.tabs.addTab(self.create_animation_tab(), self.tr['tab_animation'])
        self.tabs.addTab(self.create_about_tab(), self.tr['tab_about'])
        self.container_layout.addWidget(self.tabs)
        
        btn_layout = QHBoxLayout()
        self.reset_btn = QPushButton(self.tr['reset'])
        self.reset_btn.setObjectName("secondary")
        self.reset_btn.clicked.connect(self.reset_settings)
        btn_layout.addWidget(self.reset_btn)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton(self.tr['save'])
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)
        self.container_layout.addLayout(btn_layout)
        
        main_layout.addWidget(container)
    
    def create_general_tab(self):
        scroll = SmoothScrollArea()
        scroll.setStyleSheet("background-color: transparent;")
        
        tab = QWidget()
        tab.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(5, 5, 15, 5)
        
        lang_layout = QHBoxLayout()
        self.lang_label = QLabel(self.tr['language'])
        lang_layout.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English"])
        self.lang_combo.setCurrentIndex(0 if self.config['language'] == 'ru' else 1)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)
        
        self.autostart_check = QCheckBox(self.tr['autostart'])
        self.autostart_check.setChecked(is_autostart_enabled())
        layout.addWidget(self.autostart_check)
        
        self.topmost_check = QCheckBox(self.tr['topmost'])
        self.topmost_check.setChecked(self.config['topmost'])
        layout.addWidget(self.topmost_check)
        
        self.autohide_check = QCheckBox(self.tr['autohide'])
        self.autohide_check.setChecked(self.config['autohide'])
        layout.addWidget(self.autohide_check)
        
        pos_layout = QHBoxLayout()
        self.top_offset_label = QLabel(self.tr['top_offset'])
        pos_layout.addWidget(self.top_offset_label)
        self.top_offset = QSpinBox()
        self.top_offset.setRange(0, 100)
        self.top_offset.setValue(self.config['top_offset'])
        self.top_offset.setSuffix(" px")
        pos_layout.addWidget(self.top_offset)
        pos_layout.addStretch()
        layout.addLayout(pos_layout)
        
        monitor_layout = QHBoxLayout()
        self.monitor_label = QLabel(self.tr['monitor'])
        monitor_layout.addWidget(self.monitor_label)
        self.monitor_combo = QComboBox()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            name = f"{self.tr['monitor_primary']}" if i == 0 else f"Monitor {i + 1}"
            geo = screen.geometry()
            self.monitor_combo.addItem(f"{name} ({geo.width()}x{geo.height()})")
        if self.config['monitor'] < len(screens):
            self.monitor_combo.setCurrentIndex(self.config['monitor'])
        monitor_layout.addWidget(self.monitor_combo)
        monitor_layout.addStretch()
        layout.addLayout(monitor_layout)
        
        dc_layout = QHBoxLayout()
        self.dc_label = QLabel(self.tr['double_click'])
        dc_layout.addWidget(self.dc_label)
        self.double_click_combo = QComboBox()
        self.double_click_combo.addItems([self.tr['dc_none'], self.tr['dc_expand'], self.tr['dc_playpause'], self.tr['dc_next']])
        self.double_click_combo.setCurrentIndex(self.config.get('double_click_action', 0))
        dc_layout.addWidget(self.double_click_combo)
        dc_layout.addStretch()
        layout.addLayout(dc_layout)
        
        self.show_progress_check = QCheckBox(self.tr['show_progress'])
        self.show_progress_check.setChecked(self.config.get('show_progress_bar', True))
        layout.addWidget(self.show_progress_check)
        
        self.click_app_check = QCheckBox(self.tr['click_open_app'])
        self.click_app_check.setChecked(self.config['click_to_open_app'])
        layout.addWidget(self.click_app_check)
        
        press_layout = QHBoxLayout()
        self.long_press_label = QLabel(self.tr['long_press'])
        press_layout.addWidget(self.long_press_label)
        self.long_press_spin = QSpinBox()
        self.long_press_spin.setRange(100, 1000)
        self.long_press_spin.setValue(self.config['long_press_duration'])
        self.long_press_spin.setSuffix(" ms")
        press_layout.addWidget(self.long_press_spin)
        press_layout.addStretch()
        layout.addLayout(press_layout)
        
        self.show_remaining_check = QCheckBox(self.tr['show_remaining'])
        self.show_remaining_check.setChecked(self.config['show_time_remaining'])
        layout.addWidget(self.show_remaining_check)
        
        layout.addStretch()
        scroll.setWidget(tab)
        return scroll
    
    def on_language_changed(self, index):
        self.config['language'] = 'ru' if index == 0 else 'en'
        self.tr = TRANSLATIONS[self.config['language']]
        self.update_ui_language()
    
    def create_appearance_tab(self):
        scroll = SmoothScrollArea()
        scroll.setStyleSheet("background-color: transparent;")
        
        tab = QWidget()
        tab.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 15, 5)
        layout.setSpacing(15)
        
        size_layout = QHBoxLayout()
        self.size_lbl = QLabel(self.tr['size'])
        size_layout.addWidget(self.size_lbl)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(80, 150)
        self.size_slider.setValue(self.config['size_scale'])
        size_layout.addWidget(self.size_slider)
        self.size_label = QLabel(f"{self.config['size_scale']}%")
        size_layout.addWidget(self.size_label)
        self.size_slider.valueChanged.connect(lambda v: self.size_label.setText(f"{v}%"))
        layout.addLayout(size_layout)
        
        idle_width_layout = QHBoxLayout()
        self.idle_width_lbl = QLabel(self.tr['idle_width'])
        idle_width_layout.addWidget(self.idle_width_lbl)
        self.idle_width_spin = QSpinBox()
        self.idle_width_spin.setRange(100, 300)
        self.idle_width_spin.setValue(self.config.get('idle_width', 150))
        self.idle_width_spin.setSuffix(" px")
        idle_width_layout.addWidget(self.idle_width_spin)
        idle_width_layout.addStretch()
        layout.addLayout(idle_width_layout)
        
        media_width_layout = QHBoxLayout()
        self.media_width_lbl = QLabel(self.tr['media_width'])
        media_width_layout.addWidget(self.media_width_lbl)
        self.media_width_spin = QSpinBox()
        self.media_width_spin.setRange(150, 400)
        self.media_width_spin.setValue(self.config.get('media_width', 225))
        self.media_width_spin.setSuffix(" px")
        media_width_layout.addWidget(self.media_width_spin)
        media_width_layout.addStretch()
        layout.addLayout(media_width_layout)
        
        opacity_layout = QHBoxLayout()
        self.opacity_lbl = QLabel(self.tr['opacity'])
        opacity_layout.addWidget(self.opacity_lbl)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setValue(self.config['opacity'])
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QLabel(f"{self.config['opacity']}%")
        opacity_layout.addWidget(self.opacity_label)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        layout.addLayout(opacity_layout)
        
        radius_layout = QHBoxLayout()
        self.radius_lbl = QLabel(self.tr['corner_radius'])
        radius_layout.addWidget(self.radius_lbl)
        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setRange(10, 30)
        self.radius_slider.setValue(self.config['corner_radius'])
        radius_layout.addWidget(self.radius_slider)
        self.radius_label = QLabel(f"{self.config['corner_radius']} px")
        radius_layout.addWidget(self.radius_label)
        self.radius_slider.valueChanged.connect(lambda v: self.radius_label.setText(f"{v} px"))
        layout.addLayout(radius_layout)
        
        compact_radius_layout = QHBoxLayout()
        self.compact_radius_lbl = QLabel(self.tr['compact_radius'])
        compact_radius_layout.addWidget(self.compact_radius_lbl)
        self.compact_radius_slider = QSlider(Qt.Horizontal)
        self.compact_radius_slider.setRange(5, 25)
        self.compact_radius_slider.setValue(self.config.get('compact_corner_radius', 20))
        compact_radius_layout.addWidget(self.compact_radius_slider)
        self.compact_radius_label = QLabel(f"{self.config.get('compact_corner_radius', 20)} px")
        compact_radius_layout.addWidget(self.compact_radius_label)
        self.compact_radius_slider.valueChanged.connect(lambda v: self.compact_radius_label.setText(f"{v} px"))
        layout.addLayout(compact_radius_layout)
        
        self.eq_check = QCheckBox(self.tr['show_eq'])
        self.eq_check.setChecked(self.config['show_equalizer'])
        layout.addWidget(self.eq_check)
        
        self.eq_color_check = QCheckBox(self.tr['eq_color'])
        self.eq_color_check.setChecked(self.config['eq_color_from_art'])
        layout.addWidget(self.eq_color_check)
        
        eq_bars_layout = QHBoxLayout()
        self.eq_bars_lbl = QLabel(self.tr['eq_bars'])
        eq_bars_layout.addWidget(self.eq_bars_lbl)
        self.eq_bars_spin = QSpinBox()
        self.eq_bars_spin.setRange(3, 12)
        self.eq_bars_spin.setValue(self.config['eq_bar_count'])
        eq_bars_layout.addWidget(self.eq_bars_spin)
        eq_bars_layout.addStretch()
        layout.addLayout(eq_bars_layout)
        
        eq_sens_layout = QHBoxLayout()
        self.eq_sens_lbl = QLabel(self.tr['eq_sensitivity'])
        eq_sens_layout.addWidget(self.eq_sens_lbl)
        self.eq_sens_slider = QSlider(Qt.Horizontal)
        self.eq_sens_slider.setRange(50, 2000)
        self.eq_sens_slider.setValue(self.config.get('eq_sensitivity', 100))
        eq_sens_layout.addWidget(self.eq_sens_slider)
        self.eq_sens_label = QLabel(f"{self.config.get('eq_sensitivity', 100)}%")
        eq_sens_layout.addWidget(self.eq_sens_label)
        self.eq_sens_slider.valueChanged.connect(lambda v: self.eq_sens_label.setText(f"{v}%"))
        layout.addLayout(eq_sens_layout)
        
        layout.addStretch()
        scroll.setWidget(tab)
        return scroll
    
    def create_animation_tab(self):
        scroll = SmoothScrollArea()
        scroll.setStyleSheet("background-color: transparent;")
        
        tab = QWidget()
        tab.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        layout.setContentsMargins(5, 5, 15, 5)
        
        speed_layout = QHBoxLayout()
        self.speed_lbl = QLabel(self.tr['anim_speed'])
        speed_layout.addWidget(self.speed_lbl)
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 200)
        self.speed_slider.setValue(self.config['animation_speed'])
        speed_layout.addWidget(self.speed_slider)
        self.speed_label = QLabel(f"{self.config['animation_speed']}%")
        speed_layout.addWidget(self.speed_label)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"{v}%"))
        layout.addLayout(speed_layout)
        
        self.bounce_check = QCheckBox(self.tr['bounce'])
        self.bounce_check.setChecked(self.config['bounce_effect'])
        layout.addWidget(self.bounce_check)
        
        self.text_anim_check = QCheckBox(self.tr['text_anim'])
        self.text_anim_check.setChecked(self.config['text_animation'])
        layout.addWidget(self.text_anim_check)
        
        text_style_layout = QHBoxLayout()
        self.text_anim_style_lbl = QLabel(self.tr['text_anim_style'])
        text_style_layout.addWidget(self.text_anim_style_lbl)
        self.text_anim_style_combo = QComboBox()
        self.text_anim_style_combo.addItems([
            self.tr['text_anim_slide'],
            self.tr['text_anim_fade'],
            self.tr['text_anim_typewriter'],
            self.tr['text_anim_wave'],
            self.tr['text_anim_blur']
        ])
        self.text_anim_style_combo.setCurrentIndex(self.config.get('text_animation_style', 0))
        text_style_layout.addWidget(self.text_anim_style_combo)
        text_style_layout.addStretch()
        layout.addLayout(text_style_layout)
        
        self.btn_anim_check = QCheckBox(self.tr['btn_anim'])
        self.btn_anim_check.setChecked(self.config['button_animation'])
        layout.addWidget(self.btn_anim_check)
        
        self.flip_check = QCheckBox(self.tr['flip_anim'])
        self.flip_check.setChecked(self.config['flip_animation'])
        layout.addWidget(self.flip_check)
        
        layout.addStretch()
        scroll.setWidget(tab)
        return scroll
    
    def create_about_tab(self):
        scroll = SmoothScrollArea()
        scroll.setStyleSheet("background-color: transparent;")
        
        tab = QWidget()
        tab.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(5, 5, 15, 5)
        layout.setAlignment(Qt.AlignCenter)
        
        logo = QLabel("🏝️")
        logo.setStyleSheet("font-size: 48px;")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        
        self.about_name = QLabel(self.tr['title'])
        self.about_name.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.about_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.about_name)
        
        self.about_version = QLabel(f"{self.tr['version']} 1.0.0")
        self.about_version.setStyleSheet("color: #888888;")
        self.about_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.about_version)
        
        layout.addSpacing(20)
        
        self.about_desc = QLabel(self.tr['description'])
        self.about_desc.setStyleSheet("color: #aaaaaa;")
        self.about_desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.about_desc)
        
        layout.addSpacing(10)
        
        self.about_author = QLabel(self.tr['author'])
        self.about_author.setStyleSheet("color: #666666; font-size: 11px;")
        self.about_author.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.about_author)
        
        layout.addSpacing(20)
        
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        
        github_btn = QPushButton("GitHub")
        github_btn.setObjectName("secondary")
        github_btn.clicked.connect(lambda: __import__('webbrowser').open('https://github.com/dmavvka/Windows-Island'))
        btn_layout.addWidget(github_btn)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        scroll.setWidget(tab)
        return scroll
    
    def update_ui_language(self):
        self.tr = TRANSLATIONS[self.config['language']]
        self.title_label.setText(self.tr['title'])
        self.subtitle_label.setText(self.tr['subtitle'])
        self.tabs.setTabText(0, self.tr['tab_general'])
        self.tabs.setTabText(1, self.tr['tab_appearance'])
        self.tabs.setTabText(2, self.tr['tab_animation'])
        self.tabs.setTabText(3, self.tr['tab_about'])
        self.reset_btn.setText(self.tr['reset'])
        self.save_btn.setText(self.tr['save'])
        
        self.autostart_check.setText(self.tr['autostart'])
        self.topmost_check.setText(self.tr['topmost'])
        self.autohide_check.setText(self.tr['autohide'])
        self.click_app_check.setText(self.tr['click_open_app'])
        self.show_remaining_check.setText(self.tr['show_remaining'])
        self.show_progress_check.setText(self.tr['show_progress'])
        self.lang_label.setText(self.tr['language'])
        self.top_offset_label.setText(self.tr['top_offset'])
        self.monitor_label.setText(self.tr['monitor'])
        self.dc_label.setText(self.tr['double_click'])
        self.long_press_label.setText(self.tr['long_press'])
        
        self.eq_check.setText(self.tr['show_eq'])
        self.eq_color_check.setText(self.tr['eq_color'])
        self.size_lbl.setText(self.tr['size'])
        self.idle_width_lbl.setText(self.tr['idle_width'])
        self.media_width_lbl.setText(self.tr['media_width'])
        self.opacity_lbl.setText(self.tr['opacity'])
        self.radius_lbl.setText(self.tr['corner_radius'])
        self.compact_radius_lbl.setText(self.tr['compact_radius'])
        self.eq_bars_lbl.setText(self.tr['eq_bars'])
        self.eq_sens_lbl.setText(self.tr['eq_sensitivity'])
        
        self.bounce_check.setText(self.tr['bounce'])
        self.text_anim_check.setText(self.tr['text_anim'])
        self.btn_anim_check.setText(self.tr['btn_anim'])
        self.flip_check.setText(self.tr['flip_anim'])
        self.speed_lbl.setText(self.tr['anim_speed'])
        self.text_anim_style_lbl.setText(self.tr['text_anim_style'])
        
        current_dc = self.double_click_combo.currentIndex()
        self.double_click_combo.clear()
        self.double_click_combo.addItems([self.tr['dc_none'], self.tr['dc_expand'], self.tr['dc_playpause'], self.tr['dc_next']])
        self.double_click_combo.setCurrentIndex(current_dc)
        
        current_anim = self.text_anim_style_combo.currentIndex()
        self.text_anim_style_combo.clear()
        self.text_anim_style_combo.addItems([
            self.tr['text_anim_slide'],
            self.tr['text_anim_fade'],
            self.tr['text_anim_typewriter'],
            self.tr['text_anim_wave'],
            self.tr['text_anim_blur']
        ])
        self.text_anim_style_combo.setCurrentIndex(current_anim)
        
        current_monitor = self.monitor_combo.currentIndex()
        self.monitor_combo.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            name = f"{self.tr['monitor_primary']}" if i == 0 else f"Monitor {i + 1}"
            geo = screen.geometry()
            self.monitor_combo.addItem(f"{name} ({geo.width()}x{geo.height()})")
        self.monitor_combo.setCurrentIndex(current_monitor)
        
        self.about_name.setText(self.tr['title'])
        self.about_version.setText(f"{self.tr['version']} 1.0.0")
        self.about_desc.setText(self.tr['description'])
        self.about_author.setText(self.tr['author'])
    
    def save_settings(self):
        self.config['language'] = 'ru' if self.lang_combo.currentIndex() == 0 else 'en'
        self.config['autostart'] = self.autostart_check.isChecked()
        self.config['topmost'] = self.topmost_check.isChecked()
        self.config['autohide'] = self.autohide_check.isChecked()
        self.config['top_offset'] = self.top_offset.value()
        self.config['monitor'] = self.monitor_combo.currentIndex()
        self.config['double_click_action'] = self.double_click_combo.currentIndex()
        self.config['show_progress_bar'] = self.show_progress_check.isChecked()
        self.config['click_to_open_app'] = self.click_app_check.isChecked()
        self.config['long_press_duration'] = self.long_press_spin.value()
        self.config['show_time_remaining'] = self.show_remaining_check.isChecked()
        self.config['size_scale'] = self.size_slider.value()
        self.config['idle_width'] = self.idle_width_spin.value()
        self.config['media_width'] = self.media_width_spin.value()
        self.config['opacity'] = self.opacity_slider.value()
        self.config['corner_radius'] = self.radius_slider.value()
        self.config['compact_corner_radius'] = self.compact_radius_slider.value()
        self.config['show_equalizer'] = self.eq_check.isChecked()
        self.config['eq_color_from_art'] = self.eq_color_check.isChecked()
        self.config['eq_bar_count'] = self.eq_bars_spin.value()
        self.config['eq_sensitivity'] = self.eq_sens_slider.value()
        self.config['animation_speed'] = self.speed_slider.value()
        self.config['bounce_effect'] = self.bounce_check.isChecked()
        self.config['text_animation'] = self.text_anim_check.isChecked()
        self.config['text_animation_style'] = self.text_anim_style_combo.currentIndex()
        self.config['button_animation'] = self.btn_anim_check.isChecked()
        self.config['flip_animation'] = self.flip_check.isChecked()
        
        save_config(self.config)
        
        set_autostart(self.config['autostart'])
        
        self.settings_changed.emit(self.config)
    
    def reset_settings(self):
        self.config = DEFAULT_CONFIG.copy()
        self.lang_combo.setCurrentIndex(0 if self.config['language'] == 'ru' else 1)
        self.autostart_check.setChecked(self.config['autostart'])
        self.topmost_check.setChecked(self.config['topmost'])
        self.autohide_check.setChecked(self.config['autohide'])
        self.top_offset.setValue(self.config['top_offset'])
        self.monitor_combo.setCurrentIndex(self.config['monitor'])
        self.double_click_combo.setCurrentIndex(self.config['double_click_action'])
        self.show_progress_check.setChecked(self.config['show_progress_bar'])
        self.click_app_check.setChecked(self.config['click_to_open_app'])
        self.long_press_spin.setValue(self.config['long_press_duration'])
        self.show_remaining_check.setChecked(self.config['show_time_remaining'])
        self.size_slider.setValue(self.config['size_scale'])
        self.idle_width_spin.setValue(self.config['idle_width'])
        self.media_width_spin.setValue(self.config['media_width'])
        self.opacity_slider.setValue(self.config['opacity'])
        self.radius_slider.setValue(self.config['corner_radius'])
        self.compact_radius_slider.setValue(self.config['compact_corner_radius'])
        self.eq_check.setChecked(self.config['show_equalizer'])
        self.eq_color_check.setChecked(self.config['eq_color_from_art'])
        self.eq_bars_spin.setValue(self.config['eq_bar_count'])
        self.eq_sens_slider.setValue(self.config['eq_sensitivity'])
        self.speed_slider.setValue(self.config['animation_speed'])
        self.bounce_check.setChecked(self.config['bounce_effect'])
        self.text_anim_check.setChecked(self.config['text_animation'])
        self.text_anim_style_combo.setCurrentIndex(self.config['text_animation_style'])
        self.btn_anim_check.setChecked(self.config['button_animation'])
        self.flip_check.setChecked(self.config['flip_animation'])
        self.update_ui_language()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(26, 26, 26))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 16, 16)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, island, settings_window):
        super().__init__()
        self.island = island
        self.settings_window = settings_window
        self.tr = settings_window.tr
        
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 10, 24, 12, 6, 6)
        painter.end()
        
        self.setIcon(QIcon(pixmap))
        self.setToolTip("Windows Island")
        
        self.create_menu()
        self.activated.connect(self.on_activated)
    
    def create_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #007AFF;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3a3a3a;
                margin: 5px 10px;
            }
        """)
        
        show_action = QAction(self.tr['show_island'], menu)
        show_action.triggered.connect(self.show_island)
        menu.addAction(show_action)
        
        settings_action = QAction(self.tr['settings'], menu)
        settings_action.triggered.connect(self.show_settings)
        menu.addAction(settings_action)
        
        menu.addSeparator()
        
        quit_action = QAction(self.tr['quit'], menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        
        self.setContextMenu(menu)
    
    def on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_settings()
    
    def show_island(self):
        if self.island.is_hidden:
            self.island.show_island()
    
    def show_settings(self):
        self.settings_window.show()
        self.settings_window.activateWindow()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    font_files = [
        "SFPRODISPLAYREGULAR.OTF",
        "SFPRODISPLAYBOLD.OTF",
        "SFPRODISPLAYMEDIUM.OTF"
    ]
    for font_file in font_files:
        font_path = resource_path(font_file)
        if os.path.exists(font_path):
            QFontDatabase.addApplicationFont(font_path)
    
    island = DynamicIsland()
    island.show()
    
    hover_zone = HoverZone(island)
    hover_zone.show()
    
    settings_window = SettingsWindow(island)
    settings_window.settings_changed.connect(island.apply_settings)
    
    tray = TrayIcon(island, settings_window)
    tray.show()
    
    sys.exit(app.exec_())

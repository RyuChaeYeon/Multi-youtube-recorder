import subprocess
import threading
import time
import json
from datetime import datetime
import os
import signal
import sys
import re
from tkinter import filedialog
import tkinter as tk

def clear_screen():
    """화면을 깨끗이 지웁니다."""
    os.system('cls' if os.name == 'nt' else 'clear')

def sanitize_filename(filename):
    """파일명에서 사용할 수 없는 문자를 제거하고 길이를 제한합니다."""
    filename = re.sub(r'[\\/*?:"<>|]', '', filename)
    filename = re.sub(r'\s+', '_', filename)
    if len(filename) > 150:
        filename = filename[:150]
    return filename

class YouTubeRecorder:
    def __init__(self, config_file="channels.json"):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.base_dir, config_file)
        self.recording_processes = {}
        self.channel_states = {}
        self.stopped_channels = set()
        self.suppress_output = False
        
        # 설정 불러오기
        self.load_settings()
        self.load_config(show_loading=False)

    def load_settings(self):
        """프로그램 설정을 불러옵니다."""
        settings_file = os.path.join(self.base_dir, "settings.json")
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                base_dir = settings.get('recordings_dir')
                self.recordings_dir = os.path.join(base_dir, "recordings")
        except (FileNotFoundError, json.JSONDecodeError):
            # tkinter 루트 윈도우 생성 (보이지 않게)
            root = tk.Tk()
            root.withdraw()

            # 폴더 선택 대화상자 표시
            print("녹화 파일이 저장될 폴더를 선택해주세요...")
            base_dir = filedialog.askdirectory(
                title="녹화 파일 저장 폴더 선택",
                initialdir=self.base_dir
            )
            
            # 선택하지 않았으면 기본값 사용
            if not base_dir:
                base_dir = self.base_dir
                
            # recordings 폴더 경로 설정
            self.recordings_dir = os.path.join(base_dir, "recordings")
            
            # 설정 저장
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump({'recordings_dir': base_dir}, f, indent=4)

        # recordings 폴더가 없으면 생성
        if not os.path.exists(self.recordings_dir):
            os.makedirs(self.recordings_dir)

    def show_status_and_commands(self):
        """채널 상태와 사용 가능한 명령어를 출력합니다."""
        clear_screen()
        
        # 먼저 명령어 표시
        print("사용 가능한 명령어:")
        print("stop @채널ID   : 특정 채널 녹화 중지")
        print("start @채널ID  : 특정 채널 녹화 시작")
        print("add @채널ID    : 새로운 채널 추가")
        print("remove @채널ID : 채널 제거")
        print("quit          : 프로그램 종료")
        print()  # 빈 줄 추가
        
        # 그 다음 채널 상태 표시
        print("=== 채널 상태 ===")
        if not self.channels:
            print("등록된 채널이 없습니다.")
            print("'add @채널ID' 명령어로 채널을 추가해주세요.")
        else:
            for channel_id in self.channels.keys():
                state = "YES" if self.channel_states.get(channel_id, False) else "NO"
                print(f"{channel_id}: {state}")
        print("================")
        print(f"\n녹화 파일 저장 경로: {self.recordings_dir}")
        
        # 마지막으로 입력 프롬프트
        print("\n명령어 입력: ", end='', flush=True)

    def load_config(self, show_loading=True):
        """설정 파일에서 채널 정보를 불러옵니다."""
        if show_loading:
            clear_screen()
            print("설정 파일을 불러오는 중...")
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                channels_data = json.load(f)
                self.channels = {}
                for channel_id in channels_data:
                    if channel_id.startswith('@'):
                        url = f"https://www.youtube.com/{channel_id}/live"
                    else:
                        url = f"https://www.youtube.com/channel/{channel_id}/live"
                    self.channels[channel_id] = url
        except FileNotFoundError:
            print(f"설정 파일이 없습니다. 새로운 {self.config_file} 파일을 생성합니다.")
            self.channels = {}
            self.save_config()
            time.sleep(2)
    def save_config(self):
        """채널 정보를 파일에 저장합니다."""
        try:
            channels_list = list(self.channels.keys())
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(channels_list, f, indent=4)
        except Exception as e:
            print(f"설정 저장 중 오류 발생: {str(e)}")

    def add_channel(self, channel_id):
        """새로운 채널을 추가합니다."""
        if channel_id in self.channels:
            print(f"채널 {channel_id}는 이미 존재합니다.")
            time.sleep(2)
            self.show_status_and_commands()
            return
        
        if channel_id.startswith('@'):
            url = f"https://www.youtube.com/{channel_id}/live"
        else:
            url = f"https://www.youtube.com/channel/{channel_id}/live"
        
        self.channels[channel_id] = url
        self.save_config()
        
        thread = threading.Thread(
            target=self.start_recording,
            args=(channel_id, url),
            daemon=True
        )
        thread.start()
        
        print(f"채널 {channel_id}가 추가되었습니다.")
        time.sleep(2)
        self.show_status_and_commands()

    def remove_channel(self, channel_id):
        """채널을 제거합니다."""
        if channel_id not in self.channels:
            print(f"채널 {channel_id}를 찾을 수 없습니다.")
            time.sleep(2)
            self.show_status_and_commands()
            return
            
        if channel_id in self.recording_processes:
            self.stop_recording(channel_id)
        
        del self.channels[channel_id]
        if channel_id in self.channel_states:
            del self.channel_states[channel_id]
        if channel_id in self.stopped_channels:
            self.stopped_channels.remove(channel_id)
        
        self.save_config()
        
        print(f"채널 {channel_id}가 제거되었습니다.")
        time.sleep(2)
        self.show_status_and_commands()

    def update_channel_state(self, channel_id, is_recording):
        """채널의 현재 상태를 업데이트하고 변경 시 전체 상태를 출력합니다."""
        if channel_id not in self.channel_states or self.channel_states[channel_id] != is_recording:
            self.channel_states[channel_id] = is_recording
            if not self.suppress_output:
                self.show_status_and_commands()

    def get_stream_title(self, url):
        """스트림 제목을 가져옵니다."""
        try:
            command = ["streamlink", "--json", url]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout:
                try:
                    data = json.loads(result.stdout)
                    title = data.get('metadata', {}).get('title')
                    if title:
                        return sanitize_filename(title)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        return None
            
    def start_recording(self, channel_id, url):
        """개별 채널 녹화를 시작합니다."""
        self.update_channel_state(channel_id, False)
        current_state = False
        
        while True:
            if channel_id in self.stopped_channels:
                self.update_channel_state(channel_id, False)
                break

            try:
                title = self.get_stream_title(url)
                if not title:
                    if current_state:
                        self.update_channel_state(channel_id, False)
                        current_state = False
                    time.sleep(10)
                    continue
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.recordings_dir, f"{channel_id}_{title}_{timestamp}.ts")
                
                os.makedirs(self.recordings_dir, exist_ok=True)
                
                process = subprocess.Popen(
                    ["streamlink", "--loglevel", "error", url, "best", "-o", filename],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                
                self.recording_processes[channel_id] = process
                
                time.sleep(3)
                if process.poll() is None:
                    if not current_state:
                        self.update_channel_state(channel_id, True)
                        current_state = True
                
                process.wait()
                
                if process.returncode != 0 and current_state:
                    self.update_channel_state(channel_id, False)
                    current_state = False
                
                time.sleep(10)
                    
            except Exception:
                if current_state:
                    self.update_channel_state(channel_id, False)
                    current_state = False
                time.sleep(10)
                
    def start_all_recordings(self):
        """모든 채널의 녹화를 시작합니다."""
        if not self.channels:
            return
            
        self.suppress_output = True
        threads = []
        
        for channel_id, url in self.channels.items():
            thread = threading.Thread(
                target=self.start_recording,
                args=(channel_id, url),
                daemon=True
            )
            threads.append(thread)
            thread.start()
        
        clear_screen()
        print("채널 상태 확인 중...")
        
        initial_states_set = False
        while not initial_states_set:
            initial_states_set = True
            for channel_id in self.channels:
                if channel_id not in self.channel_states:
                    initial_states_set = False
                    break
            time.sleep(0.5)
        
        time.sleep(5)
        self.suppress_output = False
            
    def stop_recording(self, channel_id):
        """특정 채널의 녹화를 중지합니다."""
        if channel_id in self.recording_processes:
            process = self.recording_processes[channel_id]
            process.terminate()
            del self.recording_processes[channel_id]
            self.update_channel_state(channel_id, False)
            print(f"녹화 중지됨: {channel_id}")
        self.stopped_channels.add(channel_id)
            
    def stop_all_recordings(self):
        """모든 채널의 녹화를 중지합니다."""
        for channel_id in list(self.recording_processes.keys()):
            self.stop_recording(channel_id)
            
    def signal_handler(self, signum, frame):
        """프로그램 종료 시 모든 녹화를 중지합니다."""
        clear_screen()
        print("\n프로그램을 종료합니다...")
        self.stop_all_recordings()
        sys.exit(0)

    def start_recording_for_channel(self, channel_id):
        """특정 채널의 녹화를 시작합니다."""
        if channel_id not in self.channels:
            print(f"채널 {channel_id}를 찾을 수 없습니다.")
            time.sleep(2)
            self.show_status_and_commands()
            return
        
        if channel_id in self.recording_processes:
            print(f"채널 {channel_id}는 이미 녹화 중입니다.")
            time.sleep(2)
            self.show_status_and_commands()
            return
        
        if channel_id in self.stopped_channels:
            self.stopped_channels.remove(channel_id)
        
        url = self.channels[channel_id]
        thread = threading.Thread(
            target=self.start_recording,
            args=(channel_id, url),
            daemon=True
        )
        thread.start()
        print(f"채널 {channel_id} 녹화를 시작합니다.")
        time.sleep(2)
        self.show_status_and_commands()

def main():
    clear_screen()
    print("YouTube 라이브 녹화 프로그램 초기화 중...")
    print("잠시만 기다려주세요...")
    time.sleep(1)
    
    recorder = YouTubeRecorder()
    signal.signal(signal.SIGINT, recorder.signal_handler)
    signal.signal(signal.SIGTERM, recorder.signal_handler)
    
    clear_screen()
    print("채널 목록을 불러오는 중...")
    time.sleep(1)
    
    recorder.start_all_recordings()
    recorder.show_status_and_commands()
    
    try:
        while True:
            command = input().strip()
            parts = command.split()
            
            if not parts:
                recorder.show_status_and_commands()
                continue
                
            cmd = parts[0].lower()
            
            if cmd == "quit":
                clear_screen()
                print("프로그램을 종료합니다...")
                recorder.stop_all_recordings()
                break
                
            elif cmd == "stop" and len(parts) > 1:
                channel_id = parts[1]
                if channel_id in recorder.recording_processes:
                    recorder.stop_recording(channel_id)
                    recorder.show_status_and_commands()
                else:
                    print(f"{channel_id} 채널은 현재 녹화 중이 아닙니다.")
                    time.sleep(2)
                    recorder.show_status_and_commands()
                    
            elif cmd == "start" and len(parts) > 1:
                channel_id = parts[1]
                recorder.start_recording_for_channel(channel_id)

            elif cmd == "add" and len(parts) > 1:
                channel_id = parts[1]
                recorder.add_channel(channel_id)

            elif cmd == "remove" and len(parts) > 1:
                channel_id = parts[1]
                recorder.remove_channel(channel_id)
                
            else:
                print("잘못된 명령어입니다.")
                time.sleep(2)
                recorder.show_status_and_commands()
                
    except KeyboardInterrupt:
        clear_screen()
        print("\nKeyboardInterrupt를 감지했습니다.")
        recorder.stop_all_recordings()

if __name__ == "__main__":
    main()
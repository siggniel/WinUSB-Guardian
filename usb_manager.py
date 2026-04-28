import wmi
import pythoncom
import time
import ctypes
import sys
import os
import logging
import threading
import queue
import win32api
import subprocess
import winreg
import atexit
import json

WHITELIST_FILE = 'usb_whitelist.json'

def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

# 로깅 설정 (usb_events.log 파일에 저장)
logging.basicConfig(
    filename='usb_events.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 이번 세션에서 차단된 장치 ID를 추적 (메모리에만 보관)
blocked_devices = set()
blocked_devices_lock = threading.Lock()

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def disable_autorun():
    """레지스트리를 수정하여 모든 드라이브의 자동 실행(AutoRun/AutoPlay)을 시스템 전역에서 차단합니다."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
        except OSError:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        winreg.SetValueEx(key, "NoDriveTypeAutoRun", 0, winreg.REG_DWORD, 0xFF)
        winreg.CloseKey(key)
        try:
            key_cu = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        except OSError:
            key_cu = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key_cu, "NoDriveTypeAutoRun", 0, winreg.REG_DWORD, 0xFF)
        winreg.CloseKey(key_cu)
        print("[+] 자동 실행(AutoRun)이 레지스트리 레벨에서 차단되었습니다.")
        logging.info("AutoRun disabled via Registry.")
    except Exception as e:
        print(f"[-] 자동 실행 차단 실패: {e}")
        logging.error(f"Failed to modify Registry for AutoRun: {e}")

def wmi_enable_device(device_id):
    r"""
    고도화된 4단계 활성화 로직:
    1. 부모 컨트롤러(USB Mass Storage) 활성화
    2. PnP 스캔 트리거 및 하드웨어 인식 대기
    3. 자녀 장치(USBSTOR\DISK)를 찾아서 활성화 (재시도 및 로깅 강화)
    4. 최종 스토리지 온라인 처리
    """
    try:
        pythoncom.CoInitialize()
        c = wmi.WMI()
        
        # 1. 시리얼 번호 추출 (예: '1234523100002084')
        serial = device_id.split("\\")[-1].split("&")[0]
        print(f" -> 1단계: 부모 컨트롤러({device_id}) 활성화...")
        
        enabled_count = 0
        res = subprocess.run(["pnputil", "/enable-device", device_id], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if res.returncode in (0, 3010):
            enabled_count += 1
            logging.info(f"Parent enabled: {device_id}")

        # 2. 하드웨어 변경 사항 스캔 및 대기
        print(f" -> 2단계: 하드웨어 재검색 스캔 수행...")
        subprocess.run(["pnputil", "/scan-devices"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        # 3. 자녀 장치 활성화 (최대 5회 재시도 루프)
        print(f" -> 3단계: 자녀 장치(DiskDrive 등) 검색 및 활성화 시도...")
        for attempt in range(1, 6):
            time.sleep(1) # OS 장치 로드 대기
            current_found = 0
            
            # 전체 PnP 엔티티 순회하며 시리얼이 포함된 모든 장치 검사
            all_pnp = c.Win32_PnPEntity()
            for d in all_pnp:
                try:
                    did = d.DeviceID
                    # 시리얼 번호가 포함되어 있고, OK 상태가 아닌 장치(Error 22 등)를 타겟팅
                    if did and serial in did and d.ConfigManagerErrorCode != 0:
                        # 부모는 이미 활성화했으므로 자녀만 추가 활성화
                        if did != device_id:
                            res = subprocess.run(["pnputil", "/enable-device", did], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                            if res.returncode in (0, 3010):
                                current_found += 1
                                enabled_count += 1
                                print(f"    [OK] 자식 장치 발견 및 활성화: {did[:60]}...")
                                logging.info(f"Child enabled on attempt {attempt}: {did}")
                except Exception:
                    pass
            
            if current_found > 0:
                # 자식 장치를 찾아서 활성화했다면 루프 종료 가능 (일반적으로 1개)
                break
            else:
                print(f"    (시도 {attempt}) 자식 장치를 찾는 중...")
        
        return enabled_count
    except Exception as e:
        print(f"[-] 활성화 로직 중 치명적 오류: {e}")
        logging.error(f"wmi_enable_device error for {device_id}: {e}")
        return 0

def enable_device(device_id):
    """차단된 장치를 활성화하고 blocked_devices 목록에서 제거합니다."""
    print(f" -> 장치 활성화 중...")
    
    count = wmi_enable_device(device_id)
    
    with blocked_devices_lock:
        blocked_devices.discard(device_id)
    
    if count > 0:
        print(f"[+] 장치 허용 완료! ({count}개 관련 장치 레이어 활성화됨)")
        
        # 4. 최종 단계: 스토리지 캐시 업데이트 및 오프라인 디스크 강제 온라인
        print(f" -> 4단계: 볼륨 마운트 및 디스크 온라인 처리 중...")
        ps_command = """
        Update-HostStorageCache;
        Get-Disk | Where-Object IsOffline -Eq $true | Set-Disk -IsOffline $false;
        """
        subprocess.run(["powershell", "-Command", ps_command], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"[+] 모든 작업이 완료되었습니다. 이제 탐색기에서 확인해 보세요.\n")
    else:
        print(f"[-] 장치를 활성화하지 못했습니다. (이미 활성화되어 있거나 찾을 수 없음)\n")

def restore_all_blocked():
    """프로그램 종료 시 이번 세션에서 차단한 모든 장치를 복원합니다."""
    with blocked_devices_lock:
        devices_to_restore = set(blocked_devices)
    
    if not devices_to_restore:
        return
    
    print(f"\n[*] 종료 전 차단된 {len(devices_to_restore)}개 장치를 복원 중...")
    for device_id in devices_to_restore:
        enabled, _ = wmi_enable_device(device_id)
        if enabled:
            print(f" -> [복원 완료] {device_id}")
        else:
            print(f" -> [복원 실패] {device_id} (장치 관리자에서 직접 활성화하세요)")
    print("[+] 종료 전 장치 복원 완료.")

def recover_stuck_devices():
    """시작 시 이전 실행에서 비활성화된 채 남아있는 모든 관련 장치를 자동 복구합니다."""
    print("[*] 이전에 차단된 USB 관련 장치 복구 확인 중...")
    try:
        pythoncom.CoInitialize()
        c = wmi.WMI()
        recovered = 0
        for d in c.Win32_PnPEntity():
            try:
                # VID/PID가 포함된 장치나 USBSTOR 클래스 중 비활성화(22)된 것들 복구
                did = d.DeviceID
                if did and (did.startswith("USB\\VID_") or "USBSTOR" in did.upper()) and d.ConfigManagerErrorCode == 22:
                    res = subprocess.run(["pnputil", "/enable-device", did], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.returncode in (0, 3010):
                        recovered += 1
                        logging.info(f"Recovered stuck device: {did}")
            except Exception:
                pass
        if recovered > 0:
            print(f"[+] {recovered}개의 장치가 성공적으로 복구되었습니다.")
        else:
            print("[+] 복구가 필요한 비활성화된 장치가 없습니다.")
    except Exception as e:
        print(f"[-] 장치 복구 중 오류: {e}")

def prompt_user_to_enable(device_id, device_caption):
    # 보안 강화를 위해 인터랙티브 허용(y/n) 프롬프트를 제거하고 차단 알림만 표시합니다.
    print(f"\n[!] 비인가 USB 장치 차단됨: {device_caption}")
    print(f"    장치 ID: {device_id}")
    print(f"    (이 장치를 사용하려면 관리자가 수동으로 {WHITELIST_FILE} 파일에 등록해야 합니다.)\n")
    logging.info(f"Device blocked and requires manual whitelist: {device_id} ({device_caption})")

prompt_queue = queue.Queue()

def prompt_worker():
    while True:
        try:
            device_id, caption = prompt_queue.get()
            prompt_user_to_enable(device_id, caption)
            prompt_queue.task_done()
        except Exception as e:
            logging.error(f"Prompt worker error: {e}")

def ctrl_handler(ctrl_type):
    print("\n\n[!] Ctrl+C 감지 - 차단된 장치를 복원하고 종료합니다...")
    restore_all_blocked()
    os._exit(0)
    return True

def monitor_usb_events():
    # Ctrl+C 핸들러 등록
    win32api.SetConsoleCtrlHandler(ctrl_handler, True)
    # 정상 종료 시에도 장치 복원 (atexit)
    atexit.register(restore_all_blocked)

    pythoncom.CoInitialize()
    c = wmi.WMI()

    worker_thread = threading.Thread(target=prompt_worker)
    worker_thread.daemon = True
    worker_thread.start()

    print("Windows 고급 USB 감시 및 제어 모듈 시작...")
    
    # 시작 시 이전에 비활성화된 장치 복구
    recover_stuck_devices()

    # 자동 실행 전역 차단
    disable_autorun()
    
    print("새로운 USB (Storage) 장치를 모니터링합니다. (Ctrl+C로 종료)")
    print("=" * 60)
    
    watcher = c.watch_for(
        notification_type="Creation",
        wmi_class="Win32_PnPEntity",
        delay_secs=1
    )

    while True:
        try:
            device = watcher()
            device_id = device.DeviceID
            
            # Service="USBSTOR"인 장치 (USB 대용량 저장 장치 부모 컨트롤러)만 처리
            try:
                service = device.Service
            except Exception:
                service = None

            if service and service.upper() == "USBSTOR":
                print(f"\n[*] 새로운 USB 장치 연결 감지! ({time.strftime('%Y-%m-%d %H:%M:%S')})")
                print(f" - 장치 이름 : {device.Caption}")
                logging.info(f"New USB Device Detected: {device_id} ({device.Caption})")
                
                whitelist = load_whitelist()
                serial = device_id.split("\\")[-1].split("&")[0]
                
                if any(allowed_serial in serial for allowed_serial in whitelist):
                    print(f" -> [허용됨] 화이트리스트에 등록된 신뢰할 수 있는 장치입니다. (안전 활성화 진행)")
                    logging.info(f"Device allowed by whitelist: {device_id}")
                    # 이전에 차단되어 에러 상태로 남아있을 수 있으므로 강제 활성화 루틴을 거침
                    enable_device(device_id)
                    continue
                
                # OS가 장치를 완전히 인식하고 드라이버 초기화를 마칠 시간을 잠시 부여 (행 걸림 방지)
                time.sleep(2)

                # WMI 이벤트 객체에 바로 Disable() 호출
                try:
                    result = device.Disable()
                    if result[0] == 0:
                        print(" -> [차단 완료] 장치가 시스템에서 비활성화되었습니다.")
                        logging.info(f"Device AUTO-BLOCKED: {device_id}")
                        with blocked_devices_lock:
                            blocked_devices.add(device_id)
                        prompt_queue.put((device_id, device.Caption))
                    else:
                        # 폴백: pnputil
                        res2 = subprocess.run(["pnputil", "/disable-device", device_id],
                                              capture_output=True, text=True,
                                              creationflags=subprocess.CREATE_NO_WINDOW)
                        if res2.returncode == 0:
                            print(" -> [차단 완료 - pnputil] 장치가 비활성화되었습니다.")
                            with blocked_devices_lock:
                                blocked_devices.add(device_id)
                            prompt_queue.put((device_id, device.Caption))
                        else:
                            print(f" -> [차단 실패] WMI({result[0]}) / pnputil 모두 실패")
                except Exception as e:
                    logging.error(f"Disable failed for {device_id}: {e}")
                    # 폴백: pnputil 재시도
                    for attempt in range(6):
                        res2 = subprocess.run(["pnputil", "/disable-device", device_id],
                                              capture_output=True, text=True,
                                              creationflags=subprocess.CREATE_NO_WINDOW)
                        if res2.returncode == 0:
                            print(" -> [차단 완료 - pnputil] 장치가 비활성화되었습니다.")
                            with blocked_devices_lock:
                                blocked_devices.add(device_id)
                            prompt_queue.put((device_id, device.Caption))
                            break
                        time.sleep(0.5)

        except KeyboardInterrupt:
            break
        except Exception:
            pass

if __name__ == "__main__":
    if not is_admin():
        print("[!] 관리자 권한이 필요합니다. 관리자 권한으로 재실행합니다...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    monitor_usb_events()

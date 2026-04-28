import wmi
import pythoncom
import time

def monitor_usb_events():
    # COM 초기화 (스레드에서 WMI를 사용하기 위해 필요)
    pythoncom.CoInitialize()
    c = wmi.WMI()

    # Win32_PnPEntity 클래스에서 새로운 인스턴스가 생성되는 이벤트를 감시
    print("Windows USB 장치 연결 탐지 대기 중... (Ctrl+C로 종료)")
    print("USB 메모리, 마우스, 키보드 등을 연결해 보세요.")
    print("=" * 50)
    
    watcher = c.watch_for(
        notification_type="Creation",
        wmi_class="Win32_PnPEntity",
        delay_secs=2
    )

    while True:
        try:
            # 이벤트가 발생할 때까지 대기
            device = watcher()
            
            # USB 관련 장치인지 확인
            if device.DeviceID and "USB" in device.DeviceID.upper():
                print(f"[+] USB 장치 연결 감지! ({time.strftime('%Y-%m-%d %H:%M:%S')})")
                print(f" - 장치 이름 : {device.Caption}")
                print(f" - 장치 ID   : {device.DeviceID}")
                print(f" - 제조사    : {device.Manufacturer}")
                print(f" - 상태      : {device.Status}")
                print("-" * 50)
                
        except KeyboardInterrupt:
            print("\n탐지를 종료합니다.")
            break
        except Exception as e:
            # 기타 예외 발생 시 무시하고 계속 진행 (타임아웃 등)
            pass

if __name__ == "__main__":
    monitor_usb_events()

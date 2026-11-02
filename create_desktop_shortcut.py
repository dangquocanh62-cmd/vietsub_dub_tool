import os
import sys
import subprocess

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def get_desktop_dir():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(key, "Desktop")
        expanded = os.path.expandvars(val)
        if os.path.exists(expanded):
            return expanded
    except Exception:
        pass

    # Fallback to standard desktop locations
    user_prof = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    for candidate in [
        os.path.join(user_prof, "Desktop"),
        os.path.join(user_prof, "OneDrive", "Desktop"),
        os.path.join(user_prof, "OneDrive", "Máy tính"),
    ]:
        if os.path.exists(candidate):
            return candidate
    return os.path.join(user_prof, "Desktop")

def create_shortcut():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    gui_path = os.path.join(script_dir, "gui.py")
    python_dir = os.path.dirname(sys.executable)
    pythonw_exe = os.path.join(python_dir, "pythonw.exe")
    target_exe = pythonw_exe if os.path.exists(pythonw_exe) else sys.executable

    desktop_dir = get_desktop_dir()
    os.makedirs(desktop_dir, exist_ok=True)
    shortcut_path = os.path.join(desktop_dir, "Vietsub AI Tool.lnk")

    # Tạo shortcut bằng VBScript
    vbs_content = f'''Set ws = CreateObject("WScript.Shell")
Set s = ws.CreateShortcut("{shortcut_path}")
s.TargetPath = "{target_exe}"
s.Arguments = """{gui_path}"""
s.WorkingDirectory = "{script_dir}"
s.Description = "Vietsub va Long tieng AI"
s.Save
'''
    vbs_path = os.path.join(script_dir, "_temp_create_shortcut.vbs")
    try:
        with open(vbs_path, "w", encoding="utf-16") as f:
            f.write(vbs_content)
        subprocess.run(["cscript", "//nologo", vbs_path], capture_output=True, text=True)
    finally:
        if os.path.exists(vbs_path):
            os.remove(vbs_path)

    if os.path.exists(shortcut_path):
        print("✔ ĐÃ TẠO THÀNH CÔNG BIỂU TƯỢNG NGOÀI MÀN HÌNH DESKTOP!")
        print(f"  Vị trí: {shortcut_path}")
        print("  → Giờ đây bạn chỉ cần bấm đúp vào 'Vietsub AI Tool' ngoài màn hình để mở app!")
        print("    (Phần mềm sẽ khởi động mượt mà, KHÔNG hiện cửa sổ đen CMD)")
        return True
    else:
        print("✘ Chưa tạo được shortcut. Vui lòng kiểm tra quyền truy cập Desktop.")
        return False

if __name__ == "__main__":
    create_shortcut()

#!/usr/bin/env python3

import sys
import subprocess
import json
import os
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer, QTranslator, QLocale
from ui_mainwindow import Ui_HeadsetControlQt
from color_utils import set_frame_color_based_on_window
from utils import is_windows_10

if sys.platform == "win32":
    import winshell
    import darkdetect

    SETTINGS_DIR = os.path.join(os.getenv("APPDATA"), "headsetcontrol-qt")
    HEADSETCONTROL_EXECUTABLE = os.path.join("dependencies", "headsetcontrol.exe")
    STARTUP_FOLDER = winshell.startup()
else:
    SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".config", "headsetcontrol-qt")
    HEADSETCONTROL_EXECUTABLE = "headsetcontrol"
    DESKTOP_FILE_PATH = os.path.join(os.path.expanduser("~"), ".config", "autostart", "headsetcontrol-qt.desktop")

ICONS_DIR = os.path.join("icons")
APP_ICON = os.path.join(ICONS_DIR, "icon.png")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


class HeadsetControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.timer = None
        self.tray_icon = None
        self.ui = Ui_HeadsetControlQt()
        self.ui.setupUi(self)
        self.setWindowTitle("HeadsetControl-Qt")
        self.setWindowIcon(QIcon(APP_ICON))
        self.setFixedSize(self.size())
        self.led_state = None
        self.notification_sent = False
        self.init_ui()
        self.create_tray_icon()
        self.load_settings()
        self.update_headset_info()
        self.init_timer()
        self.check_startup_checkbox()
        self.set_sidetone()
        self.on_ledBox_state_changed()

    def init_ui(self):
        if app.style().objectName() != "windows11":
            self.ui.lightBatterySpinbox.setFrame(True)
            self.ui.notificationBatterySpinbox.setFrame(True)
            self.ui.themeComboBox.setFrame(True)
            if app.style().objectName() == "fusion":
                set_frame_color_based_on_window(self, self.ui.frame)
                set_frame_color_based_on_window(self, self.ui.settingsFrame)

        self.ui.ledBox.stateChanged.connect(self.on_ledBox_state_changed)
        self.ui.lightBatterySpinbox.valueChanged.connect(self.save_settings)
        self.ui.notificationBatterySpinbox.valueChanged.connect(self.save_settings)
        self.ui.startupCheckbox.stateChanged.connect(self.on_startup_checkbox_state_changed)
        self.ui.sidetoneSlider.sliderReleased.connect(self.set_sidetone)
        self.ui.themeComboBox.addItems(["System", "Light", "Dark"])
        self.ui.themeComboBox.currentIndexChanged.connect(self.on_themeComboBox_index_changed)

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(APP_ICON))
        tray_menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.toggle_window)
        tray_menu.addAction(show_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.exit_app)
        tray_menu.addAction(exit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window()

    def toggle_window(self):
        if self.isVisible():
            self.hide()
            self.tray_icon.contextMenu().actions()[0].setText("Show")
        else:
            self.show()
            self.tray_icon.contextMenu().actions()[0].setText("Hide")

    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_headset_info)
        self.timer.start(10000)

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            self.create_default_settings()
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
            self.led_state = settings.get("led_state", True)
            self.ui.ledBox.setChecked(self.led_state)
            self.ui.lightBatterySpinbox.setEnabled(self.led_state)
            self.ui.lightBatteryLabel.setEnabled(self.led_state)
            self.ui.lightBatterySpinbox.setValue(settings.get("light_battery_threshold", 20))
            self.ui.notificationBatterySpinbox.setValue(settings.get("notification_battery_threshold", 20))
            self.ui.sidetoneSlider.setValue(settings.get("sidetone", 0))
            self.ui.themeComboBox.setCurrentText(settings.get("theme", "System"))

    def save_settings(self):
        settings = {
            "led_state": self.ui.ledBox.isChecked(),
            "light_battery_threshold": self.ui.lightBatterySpinbox.value(),
            "notification_battery_threshold": self.ui.notificationBatterySpinbox.value(),
            "sidetone": self.ui.sidetoneSlider.value(),
            "theme": self.ui.themeComboBox.currentText(),
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)

    def create_default_settings(self):
        settings = {
            "led_state": True,
            "light_battery_threshold": 20,
            "light_battery_threshold" "sidetone": 0,
            "theme": "System",
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)

    def update_headset_info(self):
        command = [HEADSETCONTROL_EXECUTABLE, "-o", "json"]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags
        )
        stdout, stderr = result.communicate(timeout=10)

        if result.returncode == 0:
            data = json.loads(stdout)
            if "devices" in data and len(data["devices"]) > 0:
                headset_info = data["devices"][0]
                self.update_ui_with_headset_info(headset_info)
                self.manage_led_based_on_battery(headset_info)
                self.send_notification_based_on_battery(headset_info)
            else:
                self.no_device_found()
        else:
            print("Error running headsetcontrol:", stderr)
            self.no_device_found()

    def manage_led_based_on_battery(self, headset_info):
        if not self.ui.ledBox.isChecked():
            return

        self.ui.lightBatterySpinbox.setEnabled(True)
        self.ui.lightBatteryLabel.setEnabled(True)
        battery_info = headset_info.get("battery", {})
        battery_level = battery_info.get("level", 0)
        battery_status = battery_info.get("status", "UNKNOWN")
        available = battery_status == "BATTERY_AVAILABLE"

        if battery_level < self.ui.lightBatterySpinbox.value() and self.led_state and available:
            self.toggle_led(False)
            self.led_state = False
            self.save_settings()
        elif battery_level >= self.ui.lightBatterySpinbox.value() + 5 and not self.led_state and available:
            self.toggle_led(True)
            self.led_state = True
            self.save_settings()

    def send_notification_based_on_battery(self, headset_info):
        battery_info = headset_info.get("battery", {})
        headset_name = headset_info.get("device", "Unknown Device")
        battery_level = battery_info.get("level", 0)
        battery_status = battery_info.get("status", "UNKNOWN")
        available = battery_status == "BATTERY_AVAILABLE"

        if battery_level < self.ui.notificationBatterySpinbox.value() and not self.notification_sent and available:
            self.send_notification(
                "Low battery", f"{headset_name} has {battery_level}% battery left.", QIcon("icons/icon.png"), 3000
            )
            self.notification_sent = True
        elif battery_level >= self.ui.notificationBatterySpinbox.value() + 5 and self.notification_sent and available:
            self.notification_sent = False

    def send_notification(self, title, message, icon, duration):
        self.tray_icon.showMessage(title, message, icon, duration)

    def toggle_led(self, state):
        command = [HEADSETCONTROL_EXECUTABLE, "-l", "1" if state else "0"]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags
        )

    def update_ui_with_headset_info(self, headset_info):
        device_name = headset_info.get("device", "Unknown Device")
        capabilities = headset_info.get("capabilities_str", [])
        battery_info = headset_info.get("battery", {})

        self.ui.deviceLabel.setText(f"{device_name}")

        battery_status = battery_info.get("status", "UNKNOWN")
        if battery_status == "BATTERY_AVAILABLE":
            battery_level = battery_info.get("level", 0)
            self.ui.batteryBar.setEnabled(True)
            self.ui.batteryBar.setValue(battery_level)
            self.ui.statusLabel.setText(f"{battery_level}%")
            self.tray_icon.setToolTip(f"Battery Level: {battery_level}%")

            icon_path = self.get_battery_icon(battery_level, charging=False)
        elif battery_status == "BATTERY_CHARGING":
            self.ui.batteryBar.setEnabled(True)
            self.ui.batteryBar.setValue(0)
            self.ui.statusLabel.setText("Charging")
            self.tray_icon.setToolTip("Battery Charging")

            icon_path = self.get_battery_icon(battery_level=None, charging=True)
        else:
            self.ui.batteryBar.setEnabled(False)
            self.ui.batteryBar.setValue(0)
            self.ui.statusLabel.setText("Off")
            self.tray_icon.setToolTip("Battery Unavailable")

            icon_path = self.get_battery_icon(battery_level=None, missing=True)

        if sys.platform == "win32":
            self.tray_icon.setIcon(QIcon(icon_path))
        elif sys.platform == "linux":
            self.tray_icon.setIcon(QIcon.fromTheme(icon_path))

        if "lights" in capabilities:
            self.ui.ledBox.setEnabled(True)
            self.ui.ledLabel.setEnabled(True)
        else:
            self.ui.ledBox.setEnabled(False)
            self.ui.ledLabel.setEnabled(False)

        if "sidetone" in capabilities:
            self.ui.sidetoneSlider.setEnabled(True)
            self.ui.sidetoneLabel.setEnabled(True)
        else:
            self.ui.sidetoneSlider.setEnabled(False)
            self.ui.sidetoneLabel.setEnabled(False)

        self.toggle_ui_elements(True)

    def get_battery_icon(self, battery_level, charging=False, missing=False):
        theme = None
        if self.ui.themeComboBox.currentText() == "System":
            if sys.platform == "win32":
                dark_mode = darkdetect.isDark()
                theme = "light" if dark_mode else "dark"
            elif sys.platform == "linux":
                if os.getenv("XDG_CURRENT_DESKTOP") == "KDE":
                    theme = "symbolic"
                else:
                    # I cannot detect every desktop and settings, so assume user is using dark theme and use light icons
                    theme = "light"
        elif self.ui.themeComboBox.currentText() == "Light":
            theme = "light"
        elif self.ui.themeComboBox.currentText() == "Dark":
            theme = "dark"

        if missing:
            icon_name = f"battery-missing-{theme}"
        elif charging:
            icon_name = f"battery-100-charging-{theme}"
        else:
            if battery_level is not None:
                battery_levels = {
                    90: "100",
                    80: "090",
                    70: "080",
                    60: "070",
                    50: "060",
                    40: "050",
                    30: "040",
                    20: "030",
                    10: "020",
                    0: "010",
                }
                icon_name = None
                for level, percentage in battery_levels.items():
                    if battery_level >= level:
                        icon_name = f"battery-{percentage}-{theme}"
                        break
            else:
                icon_name = f"battery-missing-{theme}"

        if sys.platform == "win32":
            icon_name += ".png"
            icon_path = os.path.join(ICONS_DIR, icon_name)
            return icon_path
        elif sys.platform == "linux":
            icon_path = icon_name
            return icon_path

    def no_device_found(self):
        self.toggle_ui_elements(False)
        self.tray_icon.setToolTip("No Device Found")

    def on_ledBox_state_changed(self):
        lights = True if self.ui.ledBox.isChecked() else False
        self.toggle_led(lights)

        self.ui.lightBatterySpinbox.setEnabled(True if self.ui.ledBox.isChecked() else False)
        self.ui.lightBatteryLabel.setEnabled(True if self.ui.ledBox.isChecked() else False)
        self.save_settings()

    def on_themeComboBox_index_changed(self):
        self.update_headset_info()
        self.save_settings()

    def set_sidetone(self):
        sidetone_value = self.ui.sidetoneSlider.value()
        command = [HEADSETCONTROL_EXECUTABLE, "-s", str(sidetone_value)]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creation_flags
        )
        self.save_settings()

    def toggle_ui_elements(self, show):
        self.ui.deviceLabel.setVisible(show)
        self.ui.statusLabel.setVisible(show)
        self.ui.frame.setVisible(show)
        self.ui.settingsFrame.setVisible(show)
        self.ui.settingsLabel.setVisible(show)
        self.ui.notFoundLabel.setVisible(not show)

    def show_window(self):
        self.show()

    def exit_app(self):
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def on_startup_checkbox_state_changed(self):
        checked = self.ui.startupCheckbox.isChecked()

        if sys.platform == "win32":
            shortcut_path = os.path.join(winshell.startup(), "HeadsetControl-Qt.lnk")
            target_path = sys.executable
            working_directory = os.path.dirname(target_path)

            if checked:
                winshell.CreateShortcut(
                    Path=shortcut_path,
                    Target=target_path,
                    Icon=(target_path, 0),
                    Description="Launch HeadsetControl-Qt",
                    StartIn=working_directory,
                )
            else:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)

        elif sys.platform == "linux":
            if checked:
                if not os.path.exists(os.path.dirname(DESKTOP_FILE_PATH)):
                    os.makedirs(os.path.dirname(DESKTOP_FILE_PATH))

                script_folder = os.path.dirname(__file__)
                desktop_entry_content = (
                    "[Desktop Entry]\n"
                    f"Path={script_folder}\n"
                    "Type=Application\n"
                    f"Exec={sys.executable} {__file__}\n"
                    "Name=HeadsetControl-Qt\n"
                )
                with open(DESKTOP_FILE_PATH, "w") as f:
                    f.write(desktop_entry_content)
            else:
                if os.path.exists(DESKTOP_FILE_PATH):
                    os.remove(DESKTOP_FILE_PATH)

    def check_startup_checkbox(self):
        if sys.platform == "win32":
            shortcut_path = os.path.join(winshell.startup(), "HeadsetControl-Qt.lnk")
            self.ui.startupCheckbox.setChecked(os.path.exists(shortcut_path))
        elif sys.platform == "linux":
            self.ui.startupCheckbox.setChecked(os.path.exists(DESKTOP_FILE_PATH))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    translator = QTranslator()
    locale_name = QLocale.system().name()
    locale = locale_name[:2]
    if locale:
        file_name = f"tr/headsetcontrol-qt_{locale}.qm"
    else:
        file_name = None

    if file_name and translator.load(file_name):
        app.installTranslator(translator)

    if is_windows_10():
        app.setStyle("fusion")
    window = HeadsetControlApp()
    sys.exit(app.exec())

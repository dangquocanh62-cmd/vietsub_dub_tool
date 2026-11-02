#!/usr/bin/env python3
"""
Trình Chỉnh Vị Trí Trực Quan (Position Editor) cho Vietsub Dub Tool.
Sử dụng CTkToplevel + tk.Canvas cho phép xem trước và kéo-thả vị trí phụ đề/vùng che.
"""

import os
import tempfile
import subprocess
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

# Style & Colors tương thích với gui.py
COLOR_ACCENT = "#3B82F6"
COLOR_ACCENT_HOVER = "#2563EB"
COLOR_DANGER = "#DC2626"
COLOR_DANGER_HOVER = "#B91C1C"
COLOR_TEXT_MUTED = "#A3A3A3"
COLOR_CARD_BG = "#232323"

OUTLINE_BTN = {
    "fg_color": "transparent",
    "border_width": 1,
    "border_color": "#555555",
    "hover_color": "#2A2A2A",
    "text_color": "#E5E7EB",
}

PRIMARY_BTN = {
    "fg_color": COLOR_ACCENT,
    "hover_color": COLOR_ACCENT_HOVER,
    "text_color": "#FFFFFF",
}

DANGER_BTN = {
    "fg_color": COLOR_DANGER,
    "hover_color": COLOR_DANGER_HOVER,
    "text_color": "#FFFFFF",
}


class PositionEditor(ctk.CTkToplevel):
    def __init__(self, parent, video_path, current_state, on_apply_callback):
        super().__init__(parent)
        self.parent = parent
        self.video_path = video_path
        self.current_state = current_state
        self.on_apply_callback = on_apply_callback

        self.title("Kéo-thả để chỉnh vị trí")
        self.geometry("960x680")
        self.minsize(800, 550)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Trích thông tin video & tạo giao diện
        if not self._init_video_info():
            self.after(10, self._on_close)
            return

        self._build_ui()
        self.focus()

    def _on_close(self):
        if hasattr(self.parent, "_pos_editor_win") and self.parent._pos_editor_win == self:
            self.parent._pos_editor_win = None
        self.destroy()

    def _init_video_info(self):
        """Đọc kích thước video bằng ffprobe."""
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 self.video_path],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15)
            nums = [ln.strip() for ln in probe.stdout.strip().splitlines() if ln.strip().isdigit()]
            if len(nums) < 2:
                raise RuntimeError(
                    f"ffprobe không trả về đủ dữ liệu kích thước (returncode={probe.returncode}).\n"
                    f"stdout: {probe.stdout!r}\nstderr: {(probe.stderr or '')[:300]!r}")
            self.vid_w, self.vid_h = int(nums[0]), int(nums[1])
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được kích thước video: {e}")
            return False

        max_h = 420
        scale = min(1.0, max_h / self.vid_h)
        self.canvas_w, self.canvas_h = int(self.vid_w * scale), int(self.vid_h * scale)
        self.frame_png = os.path.join(tempfile.gettempdir(), "_position_preview.png")
        return self._capture_frame(3)

    def _capture_frame(self, seek_sec):
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(seek_sec), "-i", self.video_path,
                 "-vf", f"scale={self.canvas_w}:{self.canvas_h}",
                 "-frames:v", "1", self.frame_png],
                capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không trích được khung hình xem trước: {e}")
            return False
        if not os.path.exists(self.frame_png):
            messagebox.showerror("Lỗi",
                "ffmpeg không tạo được ảnh xem trước.\n\n"
                f"returncode: {result.returncode}\n"
                f"Lỗi ffmpeg: {(result.stderr or '(không có)')[-500:]}")
            return False
        return True

    def _build_ui(self):
        canvas_w, canvas_h = self.canvas_w, self.canvas_h

        # ── Header hướng dẫn ─────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            hdr,
            text="🔴 ĐỎ = vùng che phụ đề gốc   ■   🟢 XANH = vị trí phụ đề mới   ■   🟠 CAM = vùng làm mờ tuỳ chỉnh",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        ).pack(side="left")

        # ── Hàng Tua Khung Hình (Seek) ───────────────────────────────────────
        seek_row = ctk.CTkFrame(self, fg_color="transparent")
        seek_row.pack(fill="x", padx=14, pady=(2, 6))
        ctk.CTkLabel(seek_row, text="Xem khung tại giây:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        
        self.seek_var = tk.StringVar(value="3")
        seek_entry = ctk.CTkEntry(seek_row, textvariable=self.seek_var, width=60, height=28)
        seek_entry.pack(side="left", padx=(0, 6))

        self.seek_status = ctk.CTkLabel(seek_row, text="", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED)
        self.seek_status.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            seek_row, text="🔄 Làm mới khung hình",
            command=self._refresh_frame, width=130, height=28, **OUTLINE_BTN
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            seek_row, text="← Tua đến giây có phụ đề để dễ xác định vị trí",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED
        ).pack(side="left")

        # ── CheckBox Vị trí tự do ────────────────────────────────────────────
        self.free_pos_local = tk.BooleanVar(value=self.current_state.get("use_free_pos", False))
        ctk.CTkCheckBox(
            self,
            text="Dùng vị trí phụ đề tự do (bỏ chọn = dùng preset top/middle/bottom như cũ)",
            variable=self.free_pos_local,
            font=ctk.CTkFont(size=12)
        ).pack(pady=(2, 6), anchor="w", padx=14)

        # ── Layout 2 cột: Canvas (trái) & Sidebar (phải) ─────────────────────
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=14, pady=4)

        left_pane = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_pane.pack(side="left", fill="both", expand=True, padx=(0, 10))

        sidebar = ctk.CTkFrame(content_frame, width=280, fg_color=COLOR_CARD_BG, corner_radius=8)
        sidebar.pack(side="right", fill="y", padx=0)

        # Canvas vẽ trực tiếp (tk.Canvas)
        self.canvas = tk.Canvas(
            left_pane, width=canvas_w, height=canvas_h,
            bg="#1a1a1a", highlightthickness=1, highlightbackground="#444444"
        )
        self.canvas.pack(fill="both", expand=True)

        self.photo = tk.PhotoImage(file=self.frame_png)
        self.canvas_img_id = self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        # Trạng thái chỉnh sửa
        self.editor_state = {
            "mask_top":    float(self.current_state.get("mask_top", 0.75)),
            "mask_bottom": float(self.current_state.get("mask_bottom", 0.97)),
            "pos_x":       float(self.current_state.get("pos_x", 0.5)),
            "pos_y":       float(self.current_state.get("pos_y", 0.85)),
            "dragging":    None,
        }

        # Đỏ: Mask rect & lines
        self.mask_rect = self.canvas.create_rectangle(
            0, self.editor_state["mask_top"]*canvas_h, canvas_w, self.editor_state["mask_bottom"]*canvas_h,
            fill="red", stipple="gray25", outline="")
        self.top_line = self.canvas.create_line(
            0, self.editor_state["mask_top"]*canvas_h, canvas_w, self.editor_state["mask_top"]*canvas_h,
            fill="red", width=4)
        self.bottom_line = self.canvas.create_line(
            0, self.editor_state["mask_bottom"]*canvas_h, canvas_w, self.editor_state["mask_bottom"]*canvas_h,
            fill="red", width=4)

        # Xanh lam: Vạch căn giữa X
        self.center_guide_line = self.canvas.create_line(
            canvas_w / 2, 0, canvas_w / 2, canvas_h,
            fill="#29b6f6", width=2, dash=(6, 4), state="hidden"
        )

        # Xanh lá: Vùng phụ đề mới
        self.box_w, self.box_h = int(canvas_w * 0.7), 40
        def sub_box_coords():
            cx, cy = self.editor_state["pos_x"]*canvas_w, self.editor_state["pos_y"]*canvas_h
            return cx-self.box_w/2, cy-self.box_h/2, cx+self.box_w/2, cy+self.box_h/2

        self._sub_box_coords = sub_box_coords
        self.sub_box = self.canvas.create_rectangle(*sub_box_coords(), outline="#00c853", width=3)
        self.sub_label = self.canvas.create_text(
            self.editor_state["pos_x"]*canvas_w, self.editor_state["pos_y"]*canvas_h,
            text="Vùng phụ đề", fill="#00c853", font=("Arial", 11, "bold")
        )

        # Extra blur items
        self.eb_items = []
        for eb in self.current_state.get("extra_blur_rows", []):
            try:
                t, b, s, l, r = float(eb["top"]), float(eb["bottom"]), int(eb["strength"]), float(eb["left"]), float(eb["right"])
            except Exception:
                t, b, s, l, r = 0.0, 0.15, 20, 0.0, 1.0
            self.eb_items.append({"top": t, "bottom": b, "strength": s, "left": l, "right": r,
                                  "rect": None, "top_line": None, "bot_line": None,
                                  "left_line": None, "right_line": None})

        self.selected_eb = tk.IntVar(value=-1)
        self.COLORS_EB = ["#ff8c00", "#ff4500", "#ff1493", "#9400d3", "#00bcd4"]

        # Sidebar Controls
        sub_pos_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        sub_pos_frame.pack(fill="x", padx=10, pady=(12, 8))
        ctk.CTkLabel(sub_pos_frame, text="Căn chỉnh phụ đề", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 6))

        ctk.CTkButton(sub_pos_frame, text="🎯 Căn giữa ngang (50%)", command=self._center_sub_x, height=30, **OUTLINE_BTN).pack(fill="x", pady=2)
        ctk.CTkButton(sub_pos_frame, text="↕ Căn giữa dọc (50%)", command=self._center_sub_y, height=30, **OUTLINE_BTN).pack(fill="x", pady=2)
        ctk.CTkButton(sub_pos_frame, text="⏬ Căn lề dưới (85%)", command=self._bottom_sub_y, height=30, **OUTLINE_BTN).pack(fill="x", pady=2)

        ctk.CTkLabel(sidebar, text="Vùng làm mờ tuỳ chỉnh:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            sidebar, text="Kéo các đường CAM trên canvas để chỉnh Top/Bottom/Left/Right.",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED, wraplength=240, justify="left"
        ).pack(anchor="w", padx=10, pady=(0, 6))

        self.sb_inner = ctk.CTkScrollableFrame(sidebar, height=140, fg_color="transparent")
        self.sb_inner.pack(fill="x", padx=6, pady=2)

        ctk.CTkButton(sidebar, text="➕ Thêm vùng blur", command=self._add_eb, height=30, **OUTLINE_BTN).pack(fill="x", padx=10, pady=(6, 4))

        str_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        str_frame.pack(fill="x", padx=10, pady=(4, 10))
        ctk.CTkLabel(str_frame, text="Độ mờ vùng chọn:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.str_var_local = tk.StringVar(value="20")
        str_entry = ctk.CTkEntry(str_frame, textvariable=self.str_var_local, width=55, height=28)
        str_entry.pack(side="left", padx=6)

        self.str_var_local.trace_add("write", self._on_strength_change)
        self.selected_eb.trace_add("write", self._update_strength_from_sel)

        self._redraw_all_eb()

        # Canvas Mouse Events
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # Footer Info & Buttons
        self.info_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED)
        self.info_lbl.pack(pady=(2, 4))
        self._update_info_loop()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(0, 10))
        ctk.CTkButton(btn_row, text="✔ Áp dụng", command=self._apply_and_close, width=120, height=34, **PRIMARY_BTN).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Huỷ", command=self._on_close, width=100, height=34, **OUTLINE_BTN).pack(side="left", padx=8)

    def _refresh_frame(self):
        try:
            sec = float(self.seek_var.get())
        except ValueError:
            messagebox.showwarning("Không hợp lệ", "Hãy nhập số giây hợp lệ.")
            return
        self.seek_status.configure(text="Đang chụp khung hình...")
        self.update_idletasks()
        if self._capture_frame(sec):
            self.photo = tk.PhotoImage(file=self.frame_png)
            self.canvas.itemconfig(self.canvas_img_id, image=self.photo)
            self.seek_status.configure(text=f"✔ Khung tại {sec:.0f}s")
        else:
            self.seek_status.configure(text="✘ Lỗi chụp khung")

    def _redraw_mask(self):
        cw, ch = self.canvas_w, self.canvas_h
        self.canvas.coords(self.mask_rect, 0, self.editor_state["mask_top"]*ch, cw, self.editor_state["mask_bottom"]*ch)
        self.canvas.coords(self.top_line, 0, self.editor_state["mask_top"]*ch, cw, self.editor_state["mask_top"]*ch)
        self.canvas.coords(self.bottom_line, 0, self.editor_state["mask_bottom"]*ch, cw, self.editor_state["mask_bottom"]*ch)

    def _redraw_sub_box(self):
        cw, ch = self.canvas_w, self.canvas_h
        self.canvas.coords(self.sub_box, *self._sub_box_coords())
        self.canvas.coords(self.sub_label, self.editor_state["pos_x"]*cw, self.editor_state["pos_y"]*ch)

    def _eb_color(self, idx):
        return self.COLORS_EB[idx % len(self.COLORS_EB)]

    def _redraw_all_eb(self):
        cw, ch = self.canvas_w, self.canvas_h
        for i, eb in enumerate(self.eb_items):
            col = self._eb_color(i)
            lx = eb["left"] * cw;  rx = eb["right"] * cw
            ty = eb["top"] * ch;   by = eb["bottom"] * ch
            if eb["rect"] is None:
                eb["rect"]       = self.canvas.create_rectangle(lx, ty, rx, by, fill=col, stipple="gray50", outline="", tags=f"eb{i}")
                eb["top_line"]   = self.canvas.create_line(lx, ty, rx, ty, fill=col, width=3, dash=(6,3), tags=f"eb{i}")
                eb["bot_line"]   = self.canvas.create_line(lx, by, rx, by, fill=col, width=3, dash=(6,3), tags=f"eb{i}")
                eb["left_line"]  = self.canvas.create_line(lx, ty, lx, by, fill=col, width=3, dash=(4,4), tags=f"eb{i}")
                eb["right_line"] = self.canvas.create_line(rx, ty, rx, by, fill=col, width=3, dash=(4,4), tags=f"eb{i}")
            else:
                self.canvas.coords(eb["rect"],       lx, ty, rx, by)
                self.canvas.coords(eb["top_line"],   lx, ty, rx, ty)
                self.canvas.coords(eb["bot_line"],   lx, by, rx, by)
                self.canvas.coords(eb["left_line"],  lx, ty, lx, by)
                self.canvas.coords(eb["right_line"], rx, ty, rx, by)
        self.canvas.tag_raise(self.sub_box)
        self.canvas.tag_raise(self.sub_label)
        self.canvas.tag_raise(self.top_line)
        self.canvas.tag_raise(self.bottom_line)
        self.canvas.tag_raise(self.center_guide_line)
        self._refresh_sidebar()

    def _remove_eb_canvas(self, i):
        eb = self.eb_items[i]
        for cid in [eb["rect"], eb["top_line"], eb["bot_line"], eb.get("left_line"), eb.get("right_line")]:
            if cid: self.canvas.delete(cid)
        self.eb_items.pop(i)
        for e in self.eb_items:
            for cid in [e["rect"], e["top_line"], e["bot_line"], e.get("left_line"), e.get("right_line")]:
                if cid: self.canvas.delete(cid)
            e["rect"] = e["top_line"] = e["bot_line"] = e["left_line"] = e["right_line"] = None
        if self.selected_eb.get() >= len(self.eb_items):
            self.selected_eb.set(len(self.eb_items)-1)
        self._redraw_all_eb()

    def _add_eb(self):
        self.eb_items.append({"top": 0.0, "bottom": 0.15, "strength": 20, "left": 0.0, "right": 1.0,
                              "rect": None, "top_line": None, "bot_line": None,
                              "left_line": None, "right_line": None})
        self.selected_eb.set(len(self.eb_items)-1)
        self._redraw_all_eb()

    def _center_sub_x(self):
        self.editor_state["pos_x"] = 0.5
        self._redraw_sub_box()
        self.canvas.itemconfig(self.center_guide_line, state="normal")
        self.after(1000, lambda: self.canvas.itemconfig(self.center_guide_line, state="hidden"))

    def _center_sub_y(self):
        self.editor_state["pos_y"] = 0.5
        self._redraw_sub_box()

    def _bottom_sub_y(self):
        self.editor_state["pos_y"] = 0.85
        self._redraw_sub_box()

    def _refresh_sidebar(self):
        for w in self.sb_inner.winfo_children():
            w.destroy()
        for i, eb in enumerate(self.eb_items):
            col = self._eb_color(i)
            row_f = ctk.CTkFrame(self.sb_inner, fg_color="transparent")
            row_f.pack(fill="x", pady=2)

            swatch = ctk.CTkLabel(row_f, text="", fg_color=col, width=16, height=16, corner_radius=3)
            swatch.pack(side="left", padx=(4, 6))

            title_txt = f"Vùng {i+1} T:{eb['top']:.2f}→{eb['bottom']:.2f}"
            btn_sel = ctk.CTkButton(
                row_f, text=title_txt, font=ctk.CTkFont(size=11), height=26,
                command=lambda idx=i: (self.selected_eb.set(idx), self._refresh_sidebar()),
                **OUTLINE_BTN
            )
            btn_sel.pack(side="left", fill="x", expand=True, padx=(0, 4))

            ctk.CTkButton(
                row_f, text="✕", width=26, height=26, **DANGER_BTN,
                command=lambda idx=i: self._remove_eb_canvas(idx)
            ).pack(side="right")

    def _on_strength_change(self, *_):
        idx = self.selected_eb.get()
        if 0 <= idx < len(self.eb_items):
            try:
                self.eb_items[idx]["strength"] = int(self.str_var_local.get())
            except ValueError:
                pass
            self._refresh_sidebar()

    def _update_strength_from_sel(self, *_):
        idx = self.selected_eb.get()
        if 0 <= idx < len(self.eb_items):
            self.str_var_local.set(str(self.eb_items[idx]["strength"]))

    def _on_press(self, event):
        HIT = 10
        cw, ch = self.canvas_w, self.canvas_h
        for i, eb in enumerate(self.eb_items):
            ty = eb["top"]*ch;  by = eb["bottom"]*ch
            lx = eb["left"]*cw; rx = eb["right"]*cw
            if abs(event.y - ty) < HIT and lx-HIT <= event.x <= rx+HIT:
                self.editor_state["dragging"] = ("eb_top", i); self.selected_eb.set(i); return
            if abs(event.y - by) < HIT and lx-HIT <= event.x <= rx+HIT:
                self.editor_state["dragging"] = ("eb_bot", i); self.selected_eb.set(i); return
            if abs(event.x - lx) < HIT and ty-HIT <= event.y <= by+HIT:
                self.editor_state["dragging"] = ("eb_left", i); self.selected_eb.set(i); return
            if abs(event.x - rx) < HIT and ty-HIT <= event.y <= by+HIT:
                self.editor_state["dragging"] = ("eb_right", i); self.selected_eb.set(i); return
        if abs(event.y - self.editor_state["mask_top"]*ch) < HIT:
            self.editor_state["dragging"] = "top"; return
        if abs(event.y - self.editor_state["mask_bottom"]*ch) < HIT:
            self.editor_state["dragging"] = "bottom"; return
        if self.free_pos_local.get():
            x1, y1, x2, y2 = self._sub_box_coords()
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.editor_state["dragging"] = "sub"

    def _on_drag(self, event):
        cw, ch = self.canvas_w, self.canvas_h
        d = self.editor_state["dragging"]
        if d == "top":
            self.editor_state["mask_top"] = max(0.0, min(event.y/ch, self.editor_state["mask_bottom"]-0.02))
            self._redraw_mask()
        elif d == "bottom":
            self.editor_state["mask_bottom"] = min(1.0, max(event.y/ch, self.editor_state["mask_top"]+0.02))
            self._redraw_mask()
        elif d == "sub":
            raw_x = max(0.0, min(event.x / cw, 1.0))
            if abs(raw_x - 0.5) < 0.025 or abs(event.x - cw / 2) < 12:
                self.editor_state["pos_x"] = 0.5
                self.canvas.itemconfig(self.center_guide_line, state="normal")
            else:
                self.editor_state["pos_x"] = raw_x
                self.canvas.itemconfig(self.center_guide_line, state="hidden")
            self.editor_state["pos_y"] = max(0.0, min(event.y / ch, 1.0))
            self._redraw_sub_box()
        elif isinstance(d, tuple) and d[0] == "eb_top":
            self.eb_items[d[1]]["top"] = max(0.0, min(event.y/ch, self.eb_items[d[1]]["bottom"]-0.02))
            self._redraw_all_eb()
        elif isinstance(d, tuple) and d[0] == "eb_bot":
            self.eb_items[d[1]]["bottom"] = min(1.0, max(event.y/ch, self.eb_items[d[1]]["top"]+0.02))
            self._redraw_all_eb()
        elif isinstance(d, tuple) and d[0] == "eb_left":
            self.eb_items[d[1]]["left"] = max(0.0, min(event.x/cw, self.eb_items[d[1]]["right"]-0.02))
            self._redraw_all_eb()
        elif isinstance(d, tuple) and d[0] == "eb_right":
            self.eb_items[d[1]]["right"] = min(1.0, max(event.x/cw, self.eb_items[d[1]]["left"]+0.02))
            self._redraw_all_eb()

    def _on_release(self, event):
        self.editor_state["dragging"] = None
        self.canvas.itemconfig(self.center_guide_line, state="hidden")

    def _update_info_loop(self):
        idx = self.selected_eb.get()
        if 0 <= idx < len(self.eb_items):
            eb = self.eb_items[idx]
            eb_txt = (f"  |  Vùng blur #{idx+1}: "
                      f"T{eb['top']:.2f}→{eb['bottom']:.2f}  "
                      f"L{eb['left']:.2f}→R{eb['right']:.2f}")
        else:
            eb_txt = ""
        self.info_lbl.configure(
            text=f"Che: {self.editor_state['mask_top']:.3f}→{self.editor_state['mask_bottom']:.3f}  "
                 f"Phụ đề: x={self.editor_state['pos_x']:.3f} y={self.editor_state['pos_y']:.3f}{eb_txt}"
        )
        if self.winfo_exists():
            self.after(150, self._update_info_loop)

    def _apply_and_close(self):
        extra_blurs = []
        for eb in self.eb_items:
            extra_blurs.append({
                "top": eb["top"],
                "bottom": eb["bottom"],
                "strength": eb["strength"],
                "left": eb["left"],
                "right": eb["right"],
            })

        new_state = {
            "mask_top": self.editor_state["mask_top"],
            "mask_bottom": self.editor_state["mask_bottom"],
            "pos_x": self.editor_state["pos_x"],
            "pos_y": self.editor_state["pos_y"],
            "use_free_pos": self.free_pos_local.get(),
            "extra_blur_rows": extra_blurs,
        }

        if self.on_apply_callback:
            self.on_apply_callback(new_state)
        self._on_close()

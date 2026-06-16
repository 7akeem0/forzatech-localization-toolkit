# -*- coding: utf-8 -*-
# =====================================================================
#  Arabic_Hesham  --  Universal Game-Localizer GUI  (works for ANY game)
#  X/Twitter: @Arabic_Hesham      Ko-fi: ko-fi.com/arabichesham
#
#  ----------------------------------------------------------------
#  TO REUSE FOR A NEW GAME, YOU TOUCH ONLY TWO THINGS:
#
#    (1) The CONFIG block right below  -> per-game text + links.
#
#    (2) A sibling file  apply.py  -> the game's OWN install method.
#        It must expose exactly this contract (the UI calls nothing else):
#
#          find_game() -> str | None
#              Return the game folder. Return None and the UI will ask
#              the user to pick it manually.
#
#          PROGRESS_CB = None                 # module-level variable
#              The UI sets it to a callback(name: str, pct: int).
#              Call it inside your install loop with the OVERALL
#              percentage 0..100 (the UI just displays it).
#
#          main(game_path=None) -> "ok" | "already" | "nochange"
#              Do the install, return one of those three strings.
#              Any exception you raise -> the UI shows a branded error.
#
#  EVERYTHING BELOW THE CONFIG BLOCK IS CONSTANT across all games:
#  brand colours, embedded logo + icon, Arabic RTL handling (reshape
#  + bidi), the pill buttons, the dialogs, and the queue/poll loop.
#  The UI never knows which engine it is talking to -- only the
#  three contract calls above. Do not edit it per game.
#  ----------------------------------------------------------------
#
#  BUILD (PyInstaller, Windows):
#    # if your apply.py encrypts its data first:
#    python apply.py build "<mod root>"
#    python -m PyInstaller --noconfirm --clean --onefile --windowed --noupx ^
#      --name "<APP_NAME>" --icon ".\icon.ico" ^
#      --add-data "data;data" ^
#      --collect-all arabic_reshaper --collect-all bidi ^
#      --hidden-import apply --hidden-import loc_crypto ^
#      gui.py
#
#  Needs (for correct Arabic shaping/order):  arabic_reshaper, python-bidi
# =====================================================================
import os, sys, threading, queue, traceback, webbrowser

# ============== PER-GAME (the ONLY thing you edit here) ==============
#  Just the game name. The game's actual install method lives in
#  apply.py (the contract). Nothing else in this file changes per game.
GAME_NAME = "Forza Horizon 6"
# ====================================================================

# ----- brand identity: CONSTANT across every game -- do NOT edit per game -----
TITLE_TEXT  = "تعريب هشام"                     # large heading (your signature)
BTN_TEXT    = "تثبيت التعريب"                   # install button
STATUS_INIT = "اضغط للتثبيت"                    # initial status line
X_HANDLE    = "@Arabic_Hesham"                 # X/Twitter pill label + link
X_URL       = "https://x.com/Arabic_Hesham"
KOFI_TEXT   = "ادعم استمرار التعريب"            # Ko-fi pill label
KOFI_URL    = "https://ko-fi.com/arabichesham"
# window/exe title, derived automatically from GAME_NAME:
APP_NAME    = "Arabic_Hesham_" + "".join(c if c.isalnum() else "_" for c in GAME_NAME)

# =====================================================================
#  CONSTANT BELOW THIS LINE — brand assets, palette, RTL, UI, logic.
#  Do NOT edit per game. (Change the assets only if you rebrand.)
# =====================================================================

# brand logo (amber H, transparent) — embedded base64 GIF, no external file
LOGO_B64 = ("R0lGODlhQABAAIEAAPSeC/8A/wAAAAAAACH5BAEAAAEALAAAAABAAEAAQAj/AAMIHEiwoMGDCBMqXGgQgMOHEB0yZBixIoCJAy1GxKhQI0SOAT"
"yK3Lhw5EWOJlOq9AjSJMWVGluOBInQJcqZNBvixGgzJ8GeE4H6DLkzaNGhQkvCXKpSJtOnLG+KHPrzqNKpVAUm7Wg159asYMNWxZr1a82uNM0e"
"VMsT7VmyVNkWhPrxatS2dE9yhfsyr1+9Rv/mdXo34V/CMcHKHVsYqdu1j/E2tpu4bOS5l/tOFsu5s+fPGTNTtoiYtGLRWlEbVr14dMXSr0/zdU"
"3S8uy9m9OyVv02d+/KcXff1j3891PNwJEfp11XsuDlzp8vhS29qdTq069jX0m9+erB2k3jOIba/aFypuUlyvYNuXj42NHhB3evk35g9vXx30/O"
"3Px6/uOJN59+jAFIHIGh2XdebaA16OCDBwUEADs=")

# brand icon (.ico, multi-size) for the running window's titlebar + taskbar
ICO_B64 = ("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"
"CC")

# button glyphs (white, matted on each button bg)
CUP_B64 = ("R0lGODdhDgAOAIUAAP/////+/v/5+P/08//s7P/q6v/n5v/k4//d3P/Z2f/U0//Pzv/Cwf+3tv+0sv+tq/+sq/+op/+fnf+Xlf+Tkf+Pjf+Ihv"
"+Ihf+Dgf9/ff99e/98ev98ef97ef96eP95d/94dv9xbf9raf9oZf9nZP9jYP9iX/9hXv9gXf9fXf9fXP9fW/9eW/9dWv9cWf9bWP9aV/9ZVv9Y"
"Vf9XVP9XU/9WU/9VUv9UUf9TUP9TT/9RTv9OS/9IRAAAAAAAAAAAACwAAAAADgAOAAAIsABZCGThAscLGzVUDByoAkYIBhocRKChcCGKGhkATB"
"hwQAeKhSxUvCghQQQFCjFQVBTYooWFCxUsoHARw0VFFDciANgJAIGMDyReKESRQwEBEA8BqEiwwMbQHAsK5ODxIACLAwVmDL1hdMSKBgBMSMAw"
"IwWLEzsgBBgwQACCGjhiKGwIYkICAwYOQKggooXAEzrABuC5M0PCkC5EeOiwgcMGDx9K+BXYcIblyzMmswgIADs=")
CUP_H_B64 = ("R0lGODdhDgAOAIUAAP/////+/v/8/P/39//19f/x8P/u7f/t7f/r6v/p6P/o6P/k5P/i4v/g3//c2//b2v/X1v/Pzv/Kyf/Ew//Bv/+7uv+7uf"
"+6uf+3tv+wrv+qqP+npf+lo/+ioP+dm/+cmv+Ylv+Vkv+Tkf+TkP+SkP+Rjv+Qjv+Pjf+PjP+Jh/+Fgv+Cf/9+e/99ev98ef97eP96d/95dv94"
"df93dP92c/90cf90cP9zcP9zb/9yb/9ybv9xbv9xbf9wbP9vbP9rZywAAAAADgAOAAAIqgBhCIQhY8eMGzVeDBz4gkaKCCIoYEi4EMaLGyEAaB"
"igoIeLii9msMiggsMGGi4ULozh4UMHDy9k0JCh0kUODAByAmBAw8SKGQpd8HhQ4EQKCQBeNICAIygPCAZ6/KgQIEaCAxRd6HBQYMWLCQBGgqDY"
"wseFAAQICFhgQwcNhSFRaGiAAIECCx1UxBDowgfYADpzhqBIUEUJEiMSkzDBYu/AGTUiS67hGEZAADs=")
X_B64 = ("R0lGODdhDgAOAIUAAP///+jo6Obm5uXl5d/f39ra2tHR0dDQ0M/Pz87Ozs3NzcbGxsLCwrOzs7KysrCwsK+vr5GRkYyMjIWFhYODg2ZmZmVlZV"
"1dXVxcXDw8PDg4OC4uLi0tLSoqKigoKCYmJiEhISAgIBsbGxYWFhUVFRMTExISEg8PDw4ODgsLCwoKCgUFBQQEBAMDAwICAgEBAQAAAAAAAAAA"
"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwAAAAADgAOAAAIkABhCGzhQqDAFywMHlwI44XChRhCwGjhUIUFgwkvAD"
"gwAoaLFQ8ATIDBwsWLDwkAJDABwwGAARleFHQ4AgGABSEDcPBosAUMEgwAACjQgaRCmS8gCFVwgufCFQ0AELBpoKNDmSWUCvCAwqYCECYTVgAg"
"YIPAEQoARDD6ogUFDSR9ipCQouHDgnYfDsR7kKLAgAA7")

# ---- brand palette (exact) ----
BG="#0A0B0D"; SURFACE="#111114"; SURF2="#15161A"; RULE="#1F2025"
INK="#F5F6F7"; MUTED="#9CA3AF"; DIM="#6B7280"; FAINT="#4B5258"
AMBER="#F59E0B"; AMBERB="#FBBF24"
SURF3="#1A1B20"; CORAL="#FF5E5B"; CORALH="#FF7A77"
MONO="Consolas"; SANS="Segoe UI"; SEMI="Segoe UI Semibold"

def _crash(msg):
    try:
        d=os.path.dirname(os.path.abspath(sys.executable if getattr(sys,"frozen",False) else __file__))
        open(os.path.join(d,"error_log.txt"),"w",encoding="utf-8").write(msg)
    except Exception: pass
    try:
        import tkinter as tk, tkinter.messagebox as mb
        r=tk.Tk(); r.withdraw(); mb.showerror("خطأ", msg[:1500]); r.destroy()
    except Exception: pass

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, font as tkfont
    import apply as eng
except Exception:
    _crash("Startup import failed:\n"+traceback.format_exc()); sys.exit(1)

Q=queue.Queue()

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    def R(t):
        try:
            return "\n".join(get_display(arabic_reshaper.reshape(x)) for x in str(t).split("\n"))
        except Exception:
            return t
except Exception:
    def R(t): return t

def _dark_titlebar(root):
    try:
        import ctypes
        root.update_idletasks()
        hwnd=ctypes.windll.user32.GetParent(root.winfo_id())
        v=ctypes.c_int(1)
        for attr in (20,19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,attr,ctypes.byref(v),ctypes.sizeof(v))
        col=ctypes.c_int(0x000D0B0A)  # 0x00BBGGRR -> match near-black canvas (Win11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,35,ctypes.byref(col),ctypes.sizeof(col))
    except Exception: pass

def progress_cb(name,pct): Q.put(("prog",(name,pct)))

class Pill:
    def __init__(self, parent, text, icon, icon_h, fill, fillh, border, borderh, fg, url, sc=1.0):
        self.fill, self.fillh, self.border, self.borderh = fill, fillh, border, borderh
        self.icon, self.icon_h, self.up = icon, icon_h, False
        padL=int(14*sc); padR=int(16*sc); gap=int(9*sc); h=int(36*sc); ico=icon.width()
        ft=tkfont.Font(family=SEMI,size=14)
        w=padL+ico+gap+ft.measure(text)+padR
        self.c=tk.Canvas(parent,width=w,height=h+2,bg=BG,highlightthickness=0,cursor="hand2")
        self._cap(0,1,w,h+1,border,"bd")     # 1px border ring
        self._cap(1,2,w-1,h,fill,"fl")        # inner fill
        cy=1+h/2
        self.img=self.c.create_image(padL+ico/2,cy,image=icon)
        self.c.create_text(padL+ico+gap,cy,text=text,anchor="w",fill=fg,font=ft)
        self.c.bind("<Button-1>",lambda e: webbrowser.open(url))
        self.c.bind("<Enter>",self._hover)
        self.c.bind("<Leave>",self._rest)
    def _cap(self,x0,y0,x1,y1,color,tag):
        r=(y1-y0)/2
        self.c.create_oval(x0,y0,x0+2*r,y1,fill=color,outline=color,tags=tag)
        self.c.create_oval(x1-2*r,y0,x1,y1,fill=color,outline=color,tags=tag)
        self.c.create_rectangle(x0+r,y0,x1-r,y1,fill=color,outline=color,tags=tag)
    def _hover(self,e):
        if self.up: return
        self.up=True
        self.c.itemconfig("bd",fill=self.borderh,outline=self.borderh)
        self.c.itemconfig("fl",fill=self.fillh,outline=self.fillh)
        if self.icon_h: self.c.itemconfig(self.img,image=self.icon_h)
        self.c.move("all",0,-1)
    def _rest(self,e):
        if not self.up: return
        self.up=False
        self.c.itemconfig("bd",fill=self.border,outline=self.border)
        self.c.itemconfig("fl",fill=self.fill,outline=self.fill)
        self.c.itemconfig(self.img,image=self.icon)
        self.c.move("all",0,1)

class App:
    def __init__(self,root):
        self.root=root
        root.title(APP_NAME)
        try:
            import ctypes
            dpi=ctypes.windll.user32.GetDpiForSystem()
        except Exception:
            dpi=96
        SC=max(1.0, dpi/96.0)
        try: root.tk.call("tk","scaling", dpi/72.0)
        except Exception: pass
        self.SC=SC
        def s(v): return int(round(v*SC))
        self.s=s
        z=max(1,int(round(SC))); self.z=z
        def Z(data):
            im=tk.PhotoImage(data=data)
            return im.zoom(z) if z>1 else im
        self._Z=Z
        root.geometry("%dx%d"%(s(560),s(500))); root.resizable(True,True)
        root.minsize(s(500),s(470)); root.configure(bg=BG)
        st=ttk.Style(); st.theme_use("clam")
        st.configure("TFrame",background=BG)
        st.configure("T.TLabel",background=BG,foreground=INK,font=(SANS,18,"bold"))
        st.configure("H.TLabel",background=BG,foreground=AMBER,font=(MONO,11))
        st.configure("C.TLabel",background=BG,foreground=DIM,font=(SANS,9))
        st.configure("E.TLabel",background=BG,foreground=DIM,font=(MONO,9))
        st.configure("St.TLabel",background=BG,foreground=MUTED,font=(SANS,10))
        st.configure("Logo.TLabel",background=BG)
        st.configure("Amber.TButton",background=AMBER,foreground=BG,borderwidth=0,relief="flat",
                     focuscolor=AMBER,bordercolor=AMBER,lightcolor=AMBER,darkcolor=AMBER,
                     padding=s(11),font=(SANS,11,"bold"))
        st.map("Amber.TButton",
               background=[("active",AMBERB),("disabled",SURF2)],
               foreground=[("disabled",FAINT)])
        st.configure("G.Horizontal.TProgressbar",troughcolor=SURF2,background=AMBER,
                     bordercolor=RULE,lightcolor=AMBER,darkcolor=AMBER,thickness=s(8))

        # amber accent rail at the very top
        tk.Frame(root,height=s(3),bg=AMBER).pack(fill="x",side="top")

        f=ttk.Frame(root,padding=(s(26),s(16),s(26),s(22))); f.pack(fill="both",expand=True)

        self.logo_img=Z(LOGO_B64)
        self._set_window_icon()
        ttk.Label(f,image=self.logo_img,style="Logo.TLabel").pack(pady=(s(4),s(12)))

        ttk.Label(f,text=R(TITLE_TEXT),style="T.TLabel").pack(pady=(0,s(2)))
        self.cup_img=Z(CUP_B64)
        self.cup_h_img=Z(CUP_H_B64)
        self.x_img=Z(X_B64)
        pills=ttk.Frame(f); pills.pack(pady=(s(12),0))
        Pill(pills, R(KOFI_TEXT), self.cup_img, self.cup_h_img, CORAL, CORALH, CORAL, CORALH, "#FFFFFF", KOFI_URL, SC).c.pack(side="left",padx=s(5))
        Pill(pills, X_HANDLE, self.x_img, None, "#000000","#000000", "#2E2E2E","#757575", "#FFFFFF", X_URL, SC).c.pack(side="left",padx=s(5))

        tk.Frame(f,height=s(1),bg=RULE).pack(fill="x",pady=s(16))

        ttk.Label(f,text=GAME_NAME.upper(),style="E.TLabel").pack()
        self.status=ttk.Label(f,text=R(STATUS_INIT),style="St.TLabel"); self.status.pack(pady=(s(12),s(8)))
        self.bar=ttk.Progressbar(f,length=s(500),mode="determinate",maximum=100,style="G.Horizontal.TProgressbar")
        self.bar.pack(pady=(0,s(16)),fill="x")
        self.btn=ttk.Button(f,text=R(BTN_TEXT),style="Amber.TButton",command=self.start)
        self.btn.pack(fill="x")

        logwrap=tk.Frame(f,bg=SURFACE,highlightthickness=1,highlightbackground=RULE,highlightcolor=RULE)
        logwrap.pack(pady=(s(14),0),fill="both",expand=True)
        self.logbox=tk.Frame(logwrap,bg=SURFACE)
        self.logbox.pack(fill="x",padx=s(10),pady=s(8))
        self._loglines=[]
        self.seen=set()
        _dark_titlebar(root)
        root.after(100,self.poll)

    def _set_window_icon(self):
        self._ico_path=None
        try:
            import tempfile, base64
            ico=os.path.join(tempfile.gettempdir(),"ah_forza_icon.ico")
            with open(ico,"wb") as fh: fh.write(base64.b64decode(ICO_B64))
            self._ico_path=ico
            self.root.iconbitmap(ico)          # this window's titlebar + taskbar
            self.root.iconbitmap(default=ico)  # any future toplevels too
        except Exception:
            try: self.root.iconphoto(True, self.logo_img)
            except Exception: pass
    def setstatus(self,t):
        self.status.configure(text=R(t))
    def logline(self,s):
        lbl=tk.Label(self.logbox,text=R(s),bg=SURFACE,fg=DIM,font=(MONO,9),anchor="e",justify="right")
        lbl.pack(fill="x",anchor="e")
        self._loglines.append(lbl)
        if len(self._loglines)>6:
            self._loglines.pop(0).destroy()

    def _dialog(self, title, message, error=False):
        d=tk.Toplevel(self.root); d.title(title); d.configure(bg=BG)
        d.transient(self.root); d.resizable(False,False)
        try:
            if self._ico_path: d.iconbitmap(self._ico_path)
        except Exception: pass
        tk.Frame(d,height=self.s(3),bg=AMBER).pack(fill="x")
        body=ttk.Frame(d,padding=(self.s(24),self.s(18),self.s(24),self.s(20))); body.pack(fill="both",expand=True)
        if error:
            ttk.Label(body,text=R("صار خطأ ولم يكتمل التثبيت. الحل: تحقّق من سلامة ملفات اللعبة (Steam) أو أصلح اللعبة (Xbox) ثم أعد المحاولة. تأكّد أن اللعبة مقفولة أثناء التثبيت."),style="St.TLabel",justify="right",wraplength=self.s(440)).pack(anchor="e",pady=(0,self.s(10)))
            ttk.Label(body,text=R("تفاصيل الخطأ"),style="St.TLabel").pack(anchor="e")
            box=tk.Frame(body,bg=SURFACE,highlightthickness=1,highlightbackground=RULE)
            box.pack(fill="both",pady=(8,14))
            t=tk.Text(box,height=9,width=58,bg=SURFACE,fg=MUTED,relief="flat",bd=0,
                      font=(MONO,9),padx=10,pady=8,wrap="word")
            t.insert("1.0",message); t.configure(state="disabled"); t.pack(fill="both")
        else:
            ttk.Label(body,text=R(message),style="St.TLabel",justify="right",wraplength=self.s(400)).pack(pady=(self.s(8),self.s(18)))
        btn=ttk.Button(body,text=R("حسناً"),style="Amber.TButton",command=d.destroy)
        btn.pack(fill="x")
        _dark_titlebar(d)
        d.update_idletasks()
        x=self.root.winfo_x()+(self.root.winfo_width()-d.winfo_width())//2
        y=self.root.winfo_y()+(self.root.winfo_height()-d.winfo_height())//2
        d.geometry("+%d+%d"%(max(0,x),max(0,y)))
        d.grab_set(); btn.focus_set(); d.wait_window()
    def start(self):
        self.btn.configure(state="disabled"); self.bar["value"]=0; self.seen=set()
        self.setstatus("جاري التحقق من اللعبة...")
        threading.Thread(target=self.work,daemon=True).start()
    def work(self):
        try:
            g=eng.find_game()
            if not g: Q.put(("ask",None)); return
            self.run_inject(g)
        except Exception:
            Q.put(("err",traceback.format_exc()))
    def run_inject(self,g):
        try:
            eng.PROGRESS_CB=progress_cb
            eng.input=lambda *a,**k:""
            res=eng.main(game_path=g)   # "ok" | "already" | "nochange"
            Q.put(("done", res or "ok"))
        except Exception:
            Q.put(("err",traceback.format_exc()))
    def poll(self):
        try:
            while True:
                kind,val=Q.get_nowait()
                if kind=="prog":
                    name,pct=val
                    if not self.seen:                      # log once, no filenames
                        self.seen.add(1); self.logline("جارٍ تثبيت ملفات التعريب...")
                    self.bar["value"]=min(99,pct)
                    self.setstatus("جاري التثبيت... %d%%"%pct)
                elif kind=="ask":
                    self.logline("لم يتم العثور على اللعبة تلقائياً.")
                    d=filedialog.askdirectory(title="اختر مجلد اللعبة")
                    if d:
                        threading.Thread(target=lambda:self.run_inject(d),daemon=True).start()
                    else:
                        self.btn.configure(state="normal"); self.setstatus("حاول مرة أخرى.")
                elif kind=="done":
                    self.bar["value"]=100
                    if val=="already":
                        self.setstatus("التعريب مثبّت مسبقاً.")
                        self.logline("التعريب مثبّت مسبقاً على ملفات اللعبة.")
                        self._dialog("ملاحظة","التعريب مثبّت مسبقاً.\nلإعادة التثبيت: تحقق من سلامة ملفات اللعبة أولاً ثم شغّل الأداة من جديد.")
                        self.btn.configure(state="disabled")
                    elif val=="nochange":
                        self.setstatus("لم تُطبّق أي تغييرات — راجع التفاصيل.")
                        self.btn.configure(state="normal")
                    else:
                        self.setstatus("تم التثبيت بنجاح ✓  شغّل اللعبة الآن.")
                        self.logline("اكتمل التثبيت بنجاح. شغّل اللعبة الآن.")
                        self._dialog("تم","تم تثبيت التعريب بنجاح! شغّل اللعبة الآن.")
                        self.btn.configure(text=R("تم ✓"),state="disabled")
                elif kind=="err":
                    self.setstatus("حدث خطأ — راجع التفاصيل بالأسفل.")
                    self.logline("خطأ أثناء التثبيت."); self.btn.configure(state="normal")
                    self._dialog("خطأ", val[-1500:], error=True)
        except queue.Empty:
            pass
        self.root.after(100,self.poll)

def main():
    try:
        import ctypes
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor v2
        except Exception: ctypes.windll.user32.SetProcessDPIAware()
    except Exception: pass
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ArabicHesham.Forza.H6")
    except Exception: pass
    root=tk.Tk(); App(root); root.mainloop()

if __name__=="__main__":
    try: main()
    except Exception: _crash("Fatal:\n"+traceback.format_exc())

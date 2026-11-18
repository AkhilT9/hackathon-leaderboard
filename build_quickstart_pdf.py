"""
Builds a professional, clean PDF for Hackathon AI Agent Observability Quickstart Guide.
Fixes all text overlaps, uses vector bullets, and structures content chronologically:
1. 30-Second Quick Tour in Browser (No setup)
2. 1-Minute Hands-On Participant Setup (Run 1 command)
3. Feature Deep-Dive (Replay, SOS Alert, Stage HUD)
"""

import os

def escape_pdf(s: str) -> str:
    return s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

class PDFCanvas:
    def __init__(self, width=612, height=792):
        self.width = width
        self.height = height
        self.pages = []
        self._new_page()

    def _new_page(self):
        self.current_stream = []
        self.current_annots = []
        self.y = self.height - 45
        self.pages.append({
            'stream': self.current_stream,
            'annots': self.current_annots
        })

    def check_space(self, needed):
        if self.y - needed < 45:
            self._new_page()

    def set_fill(self, r, g, b):
        self.current_stream.append(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def set_stroke(self, r, g, b):
        self.current_stream.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def draw_rect(self, x, y, w, h, fill=True, stroke=False):
        op = "B" if (fill and stroke) else ("f" if fill else "S")
        self.current_stream.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} re {op}")

    def draw_text(self, text, x, y, font="F1", size=10, r=0.1, g=0.1, b=0.1):
        self.set_fill(r, g, b)
        escaped = escape_pdf(text)
        self.current_stream.append(f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({escaped}) Tj ET")

    def add_link(self, x, y, w, h, url):
        annot = (
            f"<< /Type /Annot /Subtype /Link "
            f"/Rect [{x:.1f} {y:.1f} {x+w:.1f} {y+h:.1f}] "
            f"/Border [0 0 0] "
            f"/A << /S /URI /URI ({url}) >> >>"
        )
        self.current_annots.append(annot)

    def heading1(self, text):
        self.check_space(50)
        self.draw_text(text, 50, self.y, font="F2", size=17, r=0.08, g=0.12, b=0.25)
        self.y -= 24

    def heading2(self, text, badge=""):
        self.check_space(38)
        self.draw_text(text, 50, self.y, font="F2", size=12, r=0.2, g=0.28, b=0.65)
        if badge:
            bx = 50 + len(text) * 7.2
            self.set_fill(0.9, 0.94, 1.0)
            self.draw_rect(bx, self.y - 2, len(badge)*5.5 + 8, 12, fill=True)
            self.draw_text(badge, bx + 4, self.y, font="F2", size=7.5, r=0.2, g=0.35, b=0.8)
        self.set_fill(0.85, 0.9, 0.98)
        self.draw_rect(50, self.y - 4, 512, 1.2, fill=True)
        self.y -= 18

    def heading3(self, text):
        self.check_space(24)
        self.draw_text(text, 50, self.y, font="F2", size=10, r=0.15, g=0.2, b=0.3)
        self.y -= 14

    def paragraph(self, text, size=9, r=0.25, g=0.3, b=0.35):
        self.check_space(18)
        self.draw_text(text, 50, self.y, font="F1", size=size, r=r, g=g, b=b)
        self.y -= 13

    def step_item(self, num_str, title, description, link_text="", link_url=""):
        self.check_space(34)
        # Draw number bubble
        self.set_fill(0.25, 0.35, 0.85)
        self.draw_rect(50, self.y - 4, 18, 18, fill=True)
        self.draw_text(num_str, 55, self.y, font="F2", size=9, r=1, g=1, b=1)
        
        # Step title
        self.draw_text(title, 76, self.y + 4, font="F2", size=9.5, r=0.1, g=0.15, b=0.25)
        
        # Description
        self.draw_text(description, 76, self.y - 7, font="F1", size=8.5, r=0.35, g=0.4, b=0.45)
        
        if link_text and link_url:
            lx = 76 + len(description) * 4.6
            self.draw_text(f"[{link_text}]", lx, self.y - 7, font="F2", size=8.5, r=0.15, g=0.3, b=0.85)
            self.add_link(lx, self.y - 9, len(link_text)*5.5 + 10, 11, link_url)

        self.y -= 26

    def code_box(self, code_lines, label=""):
        h = len(code_lines) * 11 + 12
        self.check_space(h + 8)
        self.set_fill(0.08, 0.11, 0.18)
        self.draw_rect(50, self.y - h + 6, 512, h, fill=True)
        cur_y = self.y - 7
        for line in code_lines:
            self.draw_text(line, 62, cur_y, font="F3", size=8, r=0.92, g=0.95, b=0.98)
            cur_y -= 11
        self.y -= (h + 8)

    def card(self, title, lines, r_bg=0.96, g_bg=0.97, b_bg=0.99, r_bar=0.2, g_bar=0.4, b_bar=0.85):
        h = len(lines) * 11.5 + 20
        self.check_space(h + 8)
        self.set_fill(r_bg, g_bg, b_bg)
        self.draw_rect(50, self.y - h + 6, 512, h, fill=True)
        self.set_fill(r_bar, g_bar, b_bar)
        self.draw_rect(50, self.y - h + 6, 3.5, h, fill=True)
        
        self.draw_text(title, 62, self.y - 6, font="F2", size=9.5, r=r_bar*0.7, g=g_bar*0.7, b=b_bar*0.7)
        cur_y = self.y - 18
        for line in lines:
            self.draw_text(line, 62, cur_y, font="F1", size=8, r=0.25, g=0.3, b=0.35)
            cur_y -= 11
        self.y -= (h + 8)

def build_pdf(filepath):
    c = PDFCanvas(width=612, height=792)

    # ==================== PAGE 1 ====================
    c.heading1("Hackathon AI Leaderboard — Quick User Guide")
    c.paragraph("Follow these exact steps to test the live system either in your browser or with your own laptop.", size=9.5, r=0.4, g=0.45, b=0.55)
    c.y -= 6

    # SECTION 1
    c.heading2("Option 1: Test in 30 Seconds (Browser Only — No Setup Needed)", badge="CLICK & EXPLORE")
    c.paragraph("If you just want to see how the system works without touching a terminal:")
    c.y -= 4

    c.step_item("1", "Open the Live Leaderboard", "Visit the public cloud dashboard in your browser:", 
                "Open Dashboard", "https://hackathon-leaderboard-6m5i.onrender.com/")

    c.step_item("2", "Click on Participant 'Akhil'", "Click on Akhil's name in the table to open his live Session Replay modal.")

    c.step_item("3", "Inspect His 175-Step Session", "See his exact tools (Bash, WebSearch, MCP), durations, retries, and Run Health score.")

    c.step_item("4", "Spot the 'Mentor SOS Alert'", "Notice the red alert banner on struggling participants (>=3 errors) so mentors can help.")

    c.step_item("5", "Switch to the Big-Screen View", "Open the auditorium stage display with top 3 podium & ticker:", 
                "Open Stage View", "https://hackathon-leaderboard-6m5i.onrender.com/stage")

    c.y -= 6

    # SECTION 2
    c.heading2("Option 2: Connect Your Own Laptop (1-Minute Participant Setup)", badge="HANDS-ON")
    c.paragraph("Supports Cursor, Claude Code, Google Antigravity, Copilot, OpenCode, and Codex.")
    c.y -= 4

    c.step_item("1", "Open Your Terminal on Your Laptop", "Open PowerShell (Windows) or Terminal (macOS / Linux).")

    c.step_item("2", "Paste the 1-Line Quick Join Command", "Run the command below (change YOUR_NAME & YOUR_TEAM):")
    
    c.paragraph("Windows PowerShell command:", size=8)
    c.code_box([
        'irm "https://hackathon-leaderboard-6m5i.onrender.com/join.ps1?name=Alex&team=TeamRocket" | iex'
    ])

    c.paragraph("macOS / Linux Terminal command:", size=8)
    c.code_box([
        'curl -fsSL "https://hackathon-leaderboard-6m5i.onrender.com/join.sh?name=Alex&team=TeamRocket" | bash'
    ])

    c.step_item("3", "Watch Your Name Appear Live!", "Refresh the dashboard — your name and team appear instantly on the leaderboard!")

    c.step_item("4", "Click Your Own Row", "Click your row to inspect your own tool calls, git commits, and health score.")

    # ==================== PAGE 2 ====================
    c.heading2("What's Happening Under the Hood? (Privacy & Telemetry)")
    
    c.card(
        "Zero-Leakage Privacy Guarantee",
        [
            "- All parsing is performed locally on your laptop by the agentplay engine.",
            "- Only numerical stats are transmitted: tool names (bash, read_file), step durations, error counts, commits.",
            "- Your source code, prompts, passwords, and API keys are completely stripped and never leave your machine."
        ],
        r_bg=0.94, g_bg=0.98, b_bg=0.95, r_bar=0.1, g_bar=0.6, b_bar=0.3
    )

    c.heading2("Feature Cheat-Sheet for Judges & Mentors")
    c.card(
        "1. Stage HUD View (/stage)",
        [
            "- Designed for venue projectors and auditorium displays.",
            "- Live Top 3 Team Podium (Gold, Silver, Bronze) updated automatically.",
            "- Rolling activity ticker shows live agent actions across all participants."
        ],
        r_bg=0.98, g_bg=0.96, b_bg=1.0, r_bar=0.5, g_bar=0.2, b_bar=0.8
    )

    c.card(
        "2. Interactive Session Replay ('See His Session')",
        [
            "- Verifies that teams built their solution with AI rather than pasting pre-written code.",
            "- Shows every tool invocation, duration in seconds, error recovery, and model spend."
        ],
        r_bg=0.95, g_bg=0.98, b_bg=1.0, r_bar=0.1, g_bar=0.45, b_bar=0.85
    )

    c.card(
        "3. Mentor SOS Early Warning Alert",
        [
            "- Flags teams that are failing builds or stuck in repetitive failure loops.",
            "- Allows organizers and technical mentors to intervene before participants get discouraged."
        ],
        r_bg=1.0, g_bg=0.95, b_bg=0.95, r_bar=0.9, g_bar=0.2, b_bar=0.2
    )

    c.heading2("Live Resource Directory")
    c.paragraph("Leaderboard:  https://hackathon-leaderboard-6m5i.onrender.com/")
    c.paragraph("Stage View:   https://hackathon-leaderboard-6m5i.onrender.com/stage")
    c.paragraph("Join Form:    https://hackathon-leaderboard-6m5i.onrender.com/join")
    c.paragraph("GitHub Repo:  https://github.com/AkhilT9/hackathon-leaderboard")

    # Assemble PDF
    total_pages = len(c.pages)
    page_start_obj = 6
    page_ref_list = [f"{page_start_obj + (i*2)} 0 R" for i in range(total_pages)]

    all_objects = {}
    all_objects[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    all_objects[2] = f"<< /Type /Pages /Kids [{' '.join(page_ref_list)}] /Count {total_pages} >>"
    all_objects[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    all_objects[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    all_objects[5] = "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"

    for i, p in enumerate(c.pages):
        p_obj_num = page_start_obj + (i * 2)
        c_obj_num = p_obj_num + 1
        
        stream_bytes = "\n".join(p['stream']).encode('latin1', errors='replace')
        annots_str = f"/Annots [{' '.join(p['annots'])}]" if p['annots'] else ""
        
        all_objects[p_obj_num] = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {c_obj_num} 0 R "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            f"{annots_str} >>"
        )
        all_objects[c_obj_num] = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n"
        ).encode('ascii') + stream_bytes + b"\nendstream"

    out = bytearray()
    out.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    xref = {}
    for obj_num in range(1, len(all_objects) + 1):
        xref[obj_num] = len(out)
        val = all_objects[obj_num]
        out.extend(f"{obj_num} 0 obj\n".encode('ascii'))
        if isinstance(val, str):
            out.extend(val.encode('latin1', errors='replace'))
        else:
            out.extend(val)
        out.extend(b"\nendobj\n")

    xref_offset = len(out)
    out.extend(f"xref\n0 {len(all_objects) + 1}\n0000000000 65535 f \n".encode('ascii'))
    for obj_num in range(1, len(all_objects) + 1):
        out.extend(f"{xref[obj_num]:010d} 00000 n \n".encode('ascii'))

    out.extend(
        f"trailer\n<< /Size {len(all_objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode('ascii')
    )

    with open(filepath, 'wb') as f:
        f.write(out)
    print(f"Generated clean {filepath} successfully with {total_pages} pages.")

if __name__ == '__main__':
    pdf_path = os.path.join(os.path.dirname(__file__), 'USER_TRYOUT_GUIDE.pdf')
    build_pdf(pdf_path)

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

logger = logging.getLogger(__name__)

def register_web_routes(app: FastAPI) -> None:
    """Mounts the interactive web interface and avatar routes on the FastAPI application."""

    # Absolute path to the lexy_avatar.png image in the workspace root
    avatar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lexy_avatar.png"))

    @app.get("/", response_class=HTMLResponse)
    def read_web_ui() -> str:
        # SECURITY: never inject the partner API key into the served HTML.
        # This page is reachable unauthenticated on the public endpoint, so
        # baking ``P2P_REGENOLD_API_KEY`` into the markup would leak it to
        # every visitor. The reviewer pastes their own key into the config
        # field (persisted client-side in localStorage); the browser sends
        # it as the ``X-Regenold-Api-Key`` header on the same-origin
        # ``/api/v1`` call. The template ships with an EMPTY key field.
        return HTML_TEMPLATE

    @app.get("/lexy_avatar.png")
    def get_lexy_avatar() -> FileResponse:
        if not os.path.exists(avatar_path):
            logger.warning("Lexy avatar image not found at expected path: %s", avatar_path)
        return FileResponse(avatar_path)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antifragile OS — Lexy Compliance Assistant</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    <!-- Marked.js for Markdown parsing -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <!-- DOMPurify — sanitize model/user markdown before innerHTML (XSS guard, R104) -->
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.7/dist/purify.min.js"></script>
    <style>
        :root {
            --bg-primary: #050814;
            --bg-secondary: #0d1226;
            --bg-glass: rgba(13, 18, 38, 0.7);
            --bg-glass-hover: rgba(22, 31, 64, 0.8);
            --accent-cyan: #00f0ff;
            --accent-cyan-rgb: 0, 240, 255;
            --accent-blue: #3b82f6;
            --accent-glow: rgba(0, 240, 255, 0.15);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-glass: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(0, 240, 255, 0.25);
            --transition-speed: 0.3s;
            --sidebar-width: 320px;
            --drawer-width: 420px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', system-ui, sans-serif;
            background-color: var(--bg-primary);
            background-image:
                radial-gradient(circle at 0% 0%, rgba(0, 240, 255, 0.06) 0%, transparent 40%),
                radial-gradient(circle at 100% 100%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 50% 50%, rgba(13, 18, 38, 0.5) 0%, #050814 100%);
            background-attachment: fixed;
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Scrollbar styles */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.01);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(0, 240, 255, 0.3);
        }

        /* Layout */
        .sidebar {
            width: var(--sidebar-width);
            background: rgba(7, 10, 22, 0.8);
            border-right: 1px solid var(--border-glass);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            z-index: 10;
            backdrop-filter: blur(20px);
        }

        .main-workspace {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
            position: relative;
            background: transparent;
        }

        .detail-drawer {
            width: var(--drawer-width);
            background: rgba(7, 10, 22, 0.85);
            border-left: 1px solid var(--border-glass);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            z-index: 10;
            backdrop-filter: blur(20px);
            transition: transform var(--transition-speed) cubic-bezier(0.16, 1, 0.3, 1),
                        width var(--transition-speed) cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
        }

        .detail-drawer.collapsed {
            width: 0;
            transform: translateX(100%);
            border-left: none;
        }

        /* Sidebar content */
        .sidebar-header {
            padding: 24px;
            border-bottom: 1px solid var(--border-glass);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-container {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .logo-text {
            font-family: 'Outfit', sans-serif;
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .logo-badge {
            background: rgba(0, 240, 255, 0.1);
            border: 1px solid rgba(0, 240, 255, 0.3);
            color: var(--accent-cyan);
            font-size: 10px;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            text-transform: uppercase;
        }

        .avatar-widget {
            padding: 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            border-bottom: 1px solid var(--border-glass);
        }

        .avatar-container {
            position: relative;
            margin-bottom: 16px;
        }

        .avatar-glow {
            position: absolute;
            top: -6px;
            left: -6px;
            right: -6px;
            bottom: -6px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(0, 240, 255, 0.4) 0%, transparent 70%);
            z-index: -1;
            animation: pulse-glow 3s infinite ease-in-out;
        }

        .avatar-img {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            border: 2px solid var(--accent-cyan);
            object-fit: cover;
            box-shadow: 0 0 20px rgba(0, 240, 255, 0.2);
            background-color: var(--bg-secondary);
        }

        .status-dot {
            position: absolute;
            bottom: 6px;
            right: 6px;
            width: 12px;
            height: 12px;
            background-color: #10b981;
            border: 2px solid var(--bg-secondary);
            border-radius: 50%;
            box-shadow: 0 0 8px #10b981;
        }

        .avatar-name {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 4px;
            color: var(--text-primary);
        }

        .avatar-title {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .system-status {
            padding: 20px;
            flex-grow: 1;
            overflow-y: auto;
        }

        .section-title {
            font-family: 'Outfit', sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .diagnostics-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-bottom: 24px;
        }

        .diagnostic-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            transition: var(--transition-speed);
        }

        .diagnostic-item:hover {
            background: rgba(255, 255, 255, 0.04);
            border-color: rgba(0, 240, 255, 0.15);
        }

        .diag-label {
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .diag-value {
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .badge-ok {
            color: #10b981;
            background: rgba(16, 185, 129, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid rgba(16, 185, 129, 0.2);
            font-size: 10px;
            font-weight: 600;
        }

        .badge-err {
            color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid rgba(239, 68, 68, 0.2);
            font-size: 10px;
            font-weight: 600;
        }

        .badge-loading {
            color: var(--accent-cyan);
            background: rgba(0, 240, 255, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid rgba(0, 240, 255, 0.2);
            font-size: 10px;
            font-weight: 600;
            animation: pulse-glow 1.5s infinite ease-in-out;
        }

        /* Config Widget */
        .config-panel {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 12px;
        }

        .form-group {
            margin-bottom: 12px;
        }

        .form-group:last-child {
            margin-bottom: 0;
        }

        .form-label {
            font-size: 11px;
            color: var(--text-secondary);
            margin-bottom: 6px;
            display: block;
            font-weight: 500;
        }

        .form-checkbox-label {
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            user-select: none;
        }

        .form-input {
            width: 100%;
            background: rgba(5, 8, 20, 0.7);
            border: 1px solid var(--border-glass);
            border-radius: 6px;
            padding: 8px 10px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            outline: none;
            transition: var(--transition-speed);
        }

        .form-input:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(0, 240, 255, 0.15);
        }

        .checkbox-input {
            appearance: none;
            width: 16px;
            height: 16px;
            border: 1px solid var(--border-glass);
            border-radius: 4px;
            background: rgba(5, 8, 20, 0.7);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition-speed);
        }

        .checkbox-input:checked {
            border-color: var(--accent-cyan);
            background: rgba(0, 240, 255, 0.15);
        }

        .checkbox-input:checked::after {
            content: '';
            width: 8px;
            height: 8px;
            background: var(--accent-cyan);
            border-radius: 2px;
            box-shadow: 0 0 5px var(--accent-cyan);
        }

        /* Workspace main */
        .workspace-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-glass);
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(5, 8, 20, 0.5);
            backdrop-filter: blur(10px);
        }

        .workspace-title-block {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .workspace-title {
            font-family: 'Outfit', sans-serif;
            font-size: 16px;
            font-weight: 600;
        }

        .workspace-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .btn-action {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-glass);
            color: var(--text-secondary);
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: var(--transition-speed);
            outline: none;
        }

        .btn-action:hover, .btn-action.active {
            background: rgba(0, 240, 255, 0.08);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(0, 240, 255, 0.1);
        }

        /* Chat view */
        .chat-scroller {
            flex-grow: 1;
            overflow-y: auto;
            padding: 32px 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .message-row {
            display: flex;
            gap: 16px;
            max-width: 800px;
            width: 100%;
        }

        .message-row.user-row {
            align-self: flex-end;
            flex-direction: row-reverse;
        }

        .message-row.assistant-row {
            align-self: flex-start;
        }

        .msg-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            flex-shrink: 0;
            overflow: hidden;
            border: 1px solid var(--border-glass);
            background: var(--bg-secondary);
        }

        .msg-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .assistant-row .msg-avatar {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.2);
        }

        .msg-bubble-container {
            display: flex;
            flex-direction: column;
            gap: 6px;
            max-width: calc(100% - 52px);
        }

        .msg-bubble {
            padding: 14px 18px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.5;
            position: relative;
        }

        .user-row .msg-bubble {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid var(--border-glass);
            border-bottom-right-radius: 2px;
            color: var(--text-primary);
        }

        .assistant-row .msg-bubble {
            background: rgba(13, 18, 38, 0.65);
            border: 1px solid var(--border-glass);
            border-bottom-left-radius: 2px;
            color: var(--text-primary);
        }

        .assistant-row .msg-bubble::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, var(--accent-cyan) 0%, transparent 100%);
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        }

        .msg-meta {
            font-size: 11px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .user-row .msg-meta {
            justify-content: flex-end;
        }

        /* Markdown formatting inside bubble */
        .msg-bubble p {
            margin-bottom: 10px;
        }

        .msg-bubble p:last-child {
            margin-bottom: 0;
        }

        .msg-bubble ul, .msg-bubble ol {
            margin-left: 20px;
            margin-bottom: 10px;
        }

        .msg-bubble li {
            margin-bottom: 4px;
        }

        .msg-bubble code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            background: rgba(255, 255, 255, 0.05);
            padding: 2px 4px;
            border-radius: 4px;
            color: #f43f5e;
        }

        /* Welcome layout */
        .welcome-container {
            max-width: 680px;
            margin: auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            padding: 40px 20px;
        }

        .welcome-icon {
            font-size: 40px;
            margin-bottom: 20px;
            animation: float 4s infinite ease-in-out;
        }

        .welcome-title {
            font-family: 'Outfit', sans-serif;
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 12px;
            background: linear-gradient(135deg, #fff 0%, #93c5fd 50%, #22d3ee 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .welcome-desc {
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 32px;
            line-height: 1.6;
        }

        .suggestion-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            width: 100%;
        }

        .suggestion-card {
            background: rgba(13, 18, 38, 0.45);
            border: 1px solid var(--border-glass);
            border-radius: 12px;
            padding: 16px;
            text-align: left;
            cursor: pointer;
            transition: var(--transition-speed);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .suggestion-card:hover {
            background: rgba(22, 31, 64, 0.6);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
            transform: translateY(-2px);
        }

        .sug-title {
            font-family: 'Outfit', sans-serif;
            font-size: 13px;
            font-weight: 600;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .sug-prompt {
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.4;
        }

        /* Input area */
        .input-area {
            padding: 24px;
            border-top: 1px solid var(--border-glass);
            background: rgba(5, 8, 20, 0.7);
            backdrop-filter: blur(10px);
        }

        .input-wrapper {
            position: relative;
            max-width: 800px;
            margin: auto;
            display: flex;
            align-items: center;
            background: rgba(13, 18, 38, 0.8);
            border: 1px solid var(--border-glass);
            border-radius: 14px;
            padding: 6px 6px 6px 16px;
            transition: var(--transition-speed);
        }

        .input-wrapper:focus-within {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 20px rgba(0, 240, 255, 0.15);
        }

        .chat-input {
            flex-grow: 1;
            background: transparent;
            border: none;
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            padding: 10px 0;
            resize: none;
            height: 40px;
            font-family: inherit;
        }

        .btn-send {
            background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-blue) 100%);
            border: none;
            color: #000;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: var(--transition-speed);
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.3);
            outline: none;
        }

        .btn-send:hover {
            box-shadow: 0 0 25px rgba(0, 240, 255, 0.5);
            transform: scale(1.05);
        }

        .btn-send:disabled {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-muted);
            box-shadow: none;
            cursor: not-allowed;
            transform: none;
        }

        /* Detail Drawer Content */
        .drawer-header {
            padding: 20px;
            border-bottom: 1px solid var(--border-glass);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .drawer-title {
            font-family: 'Outfit', sans-serif;
            font-size: 15px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .drawer-tabs {
            display: flex;
            border-bottom: 1px solid var(--border-glass);
            background: rgba(5, 8, 20, 0.3);
        }

        .drawer-tab {
            flex-grow: 1;
            padding: 12px;
            text-align: center;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            cursor: pointer;
            border-bottom: 2px solid transparent;
            transition: var(--transition-speed);
        }

        .drawer-tab:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.01);
        }

        .drawer-tab.active {
            color: var(--accent-cyan);
            border-bottom-color: var(--accent-cyan);
            background: rgba(0, 240, 255, 0.02);
        }

        .drawer-body {
            flex-grow: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .tab-content {
            display: none;
            height: 100%;
        }

        .tab-content.active {
            display: block;
        }

        /* References tab */
        .references-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .ref-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 14px;
            transition: var(--transition-speed);
        }

        .ref-card:hover {
            border-color: rgba(0, 240, 255, 0.15);
            background: rgba(255, 255, 255, 0.03);
        }

        .ref-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .ref-title {
            font-family: 'Outfit', sans-serif;
            font-size: 13px;
            font-weight: 600;
            color: var(--accent-cyan);
        }

        .ref-badge {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.2);
            color: var(--accent-blue);
            font-size: 9px;
            padding: 1px 4px;
            border-radius: 3px;
            text-transform: uppercase;
        }

        .ref-desc {
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.4;
        }

        /* Reasoning tab */
        .reasoning-scroller {
            height: 100%;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .reasoning-log-container {
            background: #02040a;
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 12px;
            overflow-x: auto;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            line-height: 1.5;
            color: #a5b4fc;
            flex-grow: 1;
            white-space: pre-wrap;
            box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.5);
        }

        /* Stats tab */
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .stat-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 10px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .stat-label {
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stat-value {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-value.highlight {
            color: var(--accent-cyan);
            text-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
        }

        .progress-bar-bg {
            background: rgba(255, 255, 255, 0.05);
            height: 4px;
            border-radius: 2px;
            overflow: hidden;
            margin-top: 4px;
        }

        .progress-bar-fill {
            background: linear-gradient(90deg, var(--accent-cyan), var(--accent-blue));
            height: 100%;
            border-radius: 2px;
            width: 0%;
            transition: width 1s ease-out;
        }

        /* Typing indicator */
        .typing-indicator {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
        }

        .typing-dot {
            width: 6px;
            height: 6px;
            background: var(--accent-cyan);
            border-radius: 50%;
            animation: bounce-dot 1.4s infinite ease-in-out both;
            box-shadow: 0 0 4px var(--accent-cyan);
        }

        .typing-dot:nth-child(1) { animation-delay: -0.32s; }
        .typing-dot:nth-child(2) { animation-delay: -0.16s; }

        /* Animations */
        @keyframes bounce-dot {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }

        @keyframes pulse-glow {
            0%, 100% { opacity: 0.5; transform: scale(1); }
            50% { opacity: 0.8; transform: scale(1.05); }
        }

        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-8px); }
        }

        /* Responsive */
        @media (max-width: 1024px) {
            .sidebar {
                display: none; /* Hide sidebar on small screens */
            }
        }
    </style>
</head>
<body>
    <!-- Sidebar -->
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="logo-container">
                <i data-lucide="shield-check" style="color: var(--accent-cyan); width: 22px; height: 22px;"></i>
                <span class="logo-text">Antifragile OS</span>
                <span class="logo-badge">RAG</span>
            </div>
        </div>

        <div class="avatar-widget">
            <div class="avatar-container">
                <div class="avatar-glow"></div>
                <img src="/lexy_avatar.png" alt="Lexy" class="avatar-img">
                <div class="status-dot"></div>
            </div>
            <h2 class="avatar-name">Lexy</h2>
            <p class="avatar-title">EU AI Act Compliance Expert</p>
        </div>

        <div class="system-status">
            <h3 class="section-title">
                <i data-lucide="activity" style="width: 12px; height: 12px;"></i>
                System Diagnostics
            </h3>
            <div class="diagnostics-list">
                <div class="diagnostic-item">
                    <span class="diag-label">
                        <i data-lucide="server" style="width: 14px; height: 14px;"></i>
                        Core API Status
                    </span>
                    <span id="diag-api" class="diag-value"><span class="badge-loading">Checking</span></span>
                </div>
                <div class="diagnostic-item">
                    <span class="diag-label">
                        <i data-lucide="brain-circuit" style="width: 14px; height: 14px;"></i>
                        LLM Provider
                    </span>
                    <span id="diag-llm" class="diag-value"><span class="badge-loading">Checking</span></span>
                </div>
                <div class="diagnostic-item">
                    <span class="diag-label">
                        <i data-lucide="database" style="width: 14px; height: 14px;"></i>
                        Knowledge Graph
                    </span>
                    <span id="diag-graph" class="diag-value"><span class="badge-loading">Checking</span></span>
                </div>
            </div>

            <h3 class="section-title">
                <i data-lucide="sliders" style="width: 12px; height: 12px;"></i>
                Session Options
            </h3>
            <div class="config-panel">
                <div class="form-group">
                    <label class="form-checkbox-label">
                        <input type="checkbox" id="opt-reasoning" class="checkbox-input" checked>
                        Include Reasoning Trace
                    </label>
                </div>
                <div class="form-group">
                    <label class="form-checkbox-label">
                        <input type="checkbox" id="opt-telemetry" class="checkbox-input" checked>
                        Include Telemetry metrics
                    </label>
                </div>
                <div class="form-group" style="margin-top: 14px;">
                    <label class="form-label">API Key Header</label>
                    <input type="password" id="cfg-api-key" class="form-input" value="" placeholder="Paste your X-Regenold-Api-Key" autocomplete="off">
                    <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">Stored only in this browser (localStorage). Never sent anywhere except this API.</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Main Workspace -->
    <div class="main-workspace">
        <div class="workspace-header">
            <div class="workspace-title-block">
                <i data-lucide="bot" style="color: var(--accent-cyan); width: 20px; height: 20px;"></i>
                <span class="workspace-title">Lexy Compliance Agent</span>
            </div>
            <div class="workspace-actions">
                <button id="btn-clear" class="btn-action" title="Clear Conversation">
                    <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i>
                </button>
                <button id="btn-toggle-drawer" class="btn-action active" title="Toggle Detail Panel">
                    <i data-lucide="sidebar-open" style="width: 16px; height: 16px;"></i>
                </button>
            </div>
        </div>

        <!-- Chat View -->
        <div class="chat-scroller" id="chat-container">
            <div class="welcome-container" id="welcome-message">
                <div class="welcome-icon">🇪🇺</div>
                <h1 class="welcome-title">EU AI Act Workspace</h1>
                <p class="welcome-desc">
                    Greetings! I am Lexy, your AI compliance copilot. Powered by the Antifragile RAG engine, I perform deep legal analysis over the EU AI Act using a hybrid Neo4j Knowledge Graph. Ask me about prohibitions, provider obligations, GPAI, risk classes, or specific articles.
                </p>
                <div class="suggestion-grid">
                    <div class="suggestion-card" onclick="selectSuggestion('Is a remote biometric identification system prohibited under Article 5?')">
                        <div class="sug-title">
                            <i data-lucide="shield-alert" style="width: 14px; height: 14px;"></i>
                            Prohibitions
                        </div>
                        <div class="sug-prompt">Is a remote biometric identification system prohibited under Article 5?</div>
                    </div>
                    <div class="suggestion-card" onclick="selectSuggestion('What obligations do providers of high-risk systems have under Article 16?')">
                        <div class="sug-title">
                            <i data-lucide="book-open" style="width: 14px; height: 14px;"></i>
                            High-Risk Systems
                        </div>
                        <div class="sug-prompt">What obligations do providers of high-risk systems have under Article 16?</div>
                    </div>
                    <div class="suggestion-card" onclick="selectSuggestion('What are the penalties for non-compliance with the EU AI Act according to Article 99?')">
                        <div class="sug-title">
                            <i data-lucide="gavel" style="width: 14px; height: 14px;"></i>
                            Sanctions
                        </div>
                        <div class="sug-prompt">What are the penalties for non-compliance with the Act under Article 99?</div>
                    </div>
                    <div class="suggestion-card" onclick="selectSuggestion('Does the EU AI Act apply to AI systems used solely for scientific research?')">
                        <div class="sug-title">
                            <i data-lucide="microscope" style="width: 14px; height: 14px;"></i>
                            Exemptions
                        </div>
                        <div class="sug-prompt">Does the EU AI Act apply to systems used solely for scientific research?</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Input Area -->
        <div class="input-area">
            <div class="input-wrapper">
                <input type="text" id="user-input" class="chat-input" placeholder="Type a compliance question..." autocomplete="off">
                <button id="btn-send" class="btn-send" disabled>
                    <i data-lucide="send" style="width: 16px; height: 16px;"></i>
                </button>
            </div>
        </div>
    </div>

    <!-- Detail Drawer -->
    <div class="detail-drawer" id="detail-drawer">
        <div class="drawer-header">
            <span class="drawer-title">
                <i data-lucide="terminal" style="color: var(--accent-cyan); width: 16px; height: 16px;"></i>
                Execution Diagnostics
            </span>
        </div>

        <div class="drawer-tabs">
            <div class="drawer-tab active" onclick="switchTab('citations')">Citations</div>
            <div class="drawer-tab" onclick="switchTab('reasoning')">Reasoning Log</div>
            <div class="drawer-tab" onclick="switchTab('telemetry')">Telemetry</div>
        </div>

        <div class="drawer-body">
            <!-- Citations Tab -->
            <div id="tab-citations" class="tab-content active">
                <div class="references-container" id="citations-container">
                    <p style="color: var(--text-muted); font-size: 13px; text-align: center; margin-top: 40px;">
                        No citations available. Submit a question to retrieve grounding data.
                    </p>
                </div>
            </div>

            <!-- Reasoning Tab -->
            <div id="tab-reasoning" class="tab-content">
                <div class="reasoning-scroller">
                    <div class="reasoning-log-container" id="reasoning-container">No reasoning trace captured. Check "Include Reasoning Trace" before sending.</div>
                </div>
            </div>

            <!-- Telemetry Tab -->
            <div id="tab-telemetry" class="tab-content">
                <div class="references-container">
                    <div class="stats-grid">
                        <div class="stat-card">
                            <span class="stat-label">Confidence Score</span>
                            <span class="stat-value highlight" id="stat-confidence">N/A</span>
                            <div class="progress-bar-bg">
                                <div class="progress-bar-fill" id="gauge-confidence"></div>
                            </div>
                        </div>
                        <div class="stat-card">
                            <span class="stat-label">Retrieval Path</span>
                            <span class="stat-value" id="stat-path" style="font-size: 13px; text-transform: uppercase; color: var(--accent-blue);">N/A</span>
                        </div>
                        <div class="stat-card">
                            <span class="stat-label">Nodes Traversed</span>
                            <span class="stat-value" id="stat-nodes">N/A</span>
                        </div>
                        <div class="stat-card">
                            <span class="stat-label">KB Version</span>
                            <span class="stat-value" id="stat-kb" style="font-size: 12px; font-family: 'JetBrains Mono', monospace;">N/A</span>
                        </div>
                        <div class="stat-card">
                            <span class="stat-label">Obligations Match</span>
                            <span class="stat-value" id="stat-obligations">N/A</span>
                        </div>
                        <div class="stat-card">
                            <span class="stat-label">Gaps Detected</span>
                            <span class="stat-value" id="stat-gaps">N/A</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Init Lucide
        lucide.createIcons();

        // State
        const messages = [];
        let isProcessing = false;

        // Elements
        const chatContainer = document.getElementById('chat-container');
        const userInput = document.getElementById('user-input');
        const btnSend = document.getElementById('btn-send');
        const btnClear = document.getElementById('btn-clear');
        const btnToggleDrawer = document.getElementById('btn-toggle-drawer');
        const detailDrawer = document.getElementById('detail-drawer');
        const welcomeMessage = document.getElementById('welcome-message');

        const cfgApiKey = document.getElementById('cfg-api-key');
        const optReasoning = document.getElementById('opt-reasoning');
        const optTelemetry = document.getElementById('opt-telemetry');

        // R104 — XSS guards. The model `answer`, the user's own input, the
        // references list, and the healthz fields all flow into the DOM. The
        // partner API key lives in localStorage on this same origin, so any
        // unsanitized HTML sink would let injected markup exfiltrate it.
        // escapeHtml() neutralises every interpolated server/user string;
        // renderMarkdown() runs marked through DOMPurify and fails safe to
        // plain text if the sanitizer didn't load.
        function escapeHtml(s) {
            const d = document.createElement('div');
            d.textContent = (s === undefined || s === null) ? '' : String(s);
            return d.innerHTML;
        }
        function renderMarkdown(text) {
            const raw = marked.parse(text || '');
            if (window.DOMPurify) return DOMPurify.sanitize(raw);
            // Fail-safe: no sanitizer loaded -> never inject raw HTML.
            return escapeHtml(text || '');
        }

        // Persist the partner API key client-side only (localStorage), so the
        // server never has to inject it into the HTML. Restore it on load and
        // save on every edit. Wrapped in try/catch because localStorage can
        // throw in private-browsing / sandboxed iframes.
        const API_KEY_STORAGE = 'regenold_api_key';
        try {
            // R104 — prefer the URL *fragment* (#key=...) over the query
            // string (?key=...). Fragments are never sent to the server, so
            // the partner key cannot land in Railway/uvicorn access logs.
            // Query-param support is kept for backward-compat with existing
            // shared links; in both cases the URL is cleaned immediately.
            const hashParams = new URLSearchParams(window.location.hash.slice(1));
            const urlParams = new URLSearchParams(window.location.search);
            const keyParam = hashParams.get('key') || urlParams.get('key');
            if (keyParam) {
                cfgApiKey.value = keyParam.trim();
                localStorage.setItem(API_KEY_STORAGE, keyParam.trim());
                // Strip both query and fragment so the key isn't shown in the
                // address bar or left behind in browser history.
                window.history.replaceState({}, document.title, window.location.pathname);
            } else {
                const savedKey = localStorage.getItem(API_KEY_STORAGE);
                if (savedKey) cfgApiKey.value = savedKey;
            }
        } catch (e) { /* localStorage unavailable — field stays empty */ }
        cfgApiKey.addEventListener('change', () => {
            try { localStorage.setItem(API_KEY_STORAGE, cfgApiKey.value.trim()); } catch (e) {}
        });

        // References lookup for beautiful details
        const articlesSummary = {
            "Article 5": "Prohibited AI Practices — Catalogues systems presenting unacceptable risks such as cognitive behavioral manipulation, biometric categorization, and real-time biometric identification.",
            "Article 6": "Classification Rules for High-Risk AI Systems — Establishes criteria for systems requiring pre-market conformity assessment based on safety components and Annex III lists.",
            "Article 13": "Transparency and Provision of Information — Mandates high-risk systems to operate with sufficient transparency to enable deployers to interpret outputs and use the system appropriately.",
            "Article 16": "Obligations of Providers of High-Risk Systems — Details core duties including quality management systems, logging, conformity assessments, and CE marking.",
            "Article 26": "Obligations of Deployers of High-Risk Systems — Requires compliance with instructions for use, human oversight, logging, and monitoring of system operations.",
            "Article 52": "Transparency Obligations for Certain AI Systems — Imposes specific notice duties for systems interacting with humans (chatbots), emotion recognition, biometric categorization, and deepfakes.",
            "Article 99": "Penalties and Administrative Fines — Establishes financial sanctions for infringements of prohibitions (up to €35M / 7% turnover) and general obligations.",
            "Annex III": "High-Risk AI Systems — Explicit lists of applications deemed high-risk, including biometrics, critical infrastructure, education, employment, and law enforcement.",
            "Annex IV": "Technical Documentation — Details the required documentation for high-risk systems, including system architecture, risk management, data governance, and monitoring schemes."
        };

        // Event Listeners
        userInput.addEventListener('input', () => {
            btnSend.disabled = userInput.value.trim() === '' || isProcessing;
        });

        userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !btnSend.disabled) {
                sendMessage();
            }
        });

        btnSend.addEventListener('click', sendMessage);

        btnClear.addEventListener('click', () => {
            if (confirm('Clear entire conversation history?')) {
                messages.length = 0;
                chatContainer.innerHTML = '';
                chatContainer.appendChild(welcomeMessage);
                resetDiagnostics();
            }
        });

        btnToggleDrawer.addEventListener('click', () => {
            detailDrawer.classList.toggle('collapsed');
            btnToggleDrawer.classList.toggle('active');
        });

        // Initialize Diagnostics
        checkSystemHealth();

        // Functions
        async function checkSystemHealth() {
            // Healthz Check
            try {
                const res = await fetch('/healthz');
                if (res.ok) {
                    const data = await res.json();
                    document.getElementById('diag-api').innerHTML = `<span class="badge-ok">OK (v${escapeHtml(data.version || '0.1.0')})</span>`;
                } else {
                    document.getElementById('diag-api').innerHTML = '<span class="badge-err">Error</span>';
                }
            } catch (e) {
                document.getElementById('diag-api').innerHTML = '<span class="badge-err">Offline</span>';
            }

            // LLM Check
            try {
                const res = await fetch('/healthz/llm');
                if (res.ok) {
                    const data = await res.json();
                    if (data.llm_ok) {
                        document.getElementById('diag-llm').innerHTML = `<span class="badge-ok" title="${escapeHtml(data.detail || '')}">${escapeHtml(data.provider || 'Ready')}</span>`;
                    } else {
                        document.getElementById('diag-llm').innerHTML = `<span class="badge-err" title="${escapeHtml(data.detail || '')}">Fail</span>`;
                    }
                } else {
                    document.getElementById('diag-llm').innerHTML = '<span class="badge-err">Error</span>';
                }
            } catch (e) {
                document.getElementById('diag-llm').innerHTML = '<span class="badge-err">Offline</span>';
            }

            // Graph Check
            try {
                const res = await fetch('/healthz/graph');
                if (res.ok) {
                    const data = await res.json();
                    if (data.graph_ok) {
                        document.getElementById('diag-graph').innerHTML = `<span class="badge-ok" title="${escapeHtml(data.detail || '')}">Neo4j</span>`;
                    } else {
                        document.getElementById('diag-graph').innerHTML = `<span class="badge-err" title="${escapeHtml(data.detail || '')}">No Conn</span>`;
                    }
                } else {
                    document.getElementById('diag-graph').innerHTML = '<span class="badge-err">Error</span>';
                }
            } catch (e) {
                document.getElementById('diag-graph').innerHTML = '<span class="badge-err">Offline</span>';
            }
        }

        function selectSuggestion(text) {
            userInput.value = text;
            btnSend.disabled = false;
            sendMessage();
        }

        function resetDiagnostics() {
            document.getElementById('citations-container').innerHTML = `
                <p style="color: var(--text-muted); font-size: 13px; text-align: center; margin-top: 40px;">
                    No citations available. Submit a question to retrieve grounding data.
                </p>`;
            document.getElementById('reasoning-container').innerText = 'No reasoning trace captured. Check "Include Reasoning Trace" before sending.';
            document.getElementById('stat-confidence').innerText = 'N/A';
            document.getElementById('gauge-confidence').style.width = '0%';
            document.getElementById('stat-path').innerText = 'N/A';
            document.getElementById('stat-nodes').innerText = 'N/A';
            document.getElementById('stat-kb').innerText = 'N/A';
            document.getElementById('stat-obligations').innerText = 'N/A';
            document.getElementById('stat-gaps').innerText = 'N/A';
        }

        function switchTab(tabId) {
            document.querySelectorAll('.drawer-tab').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));

            // Activate current
            const tabElements = document.querySelectorAll('.drawer-tab');
            if (tabId === 'citations') tabElements[0].classList.add('active');
            if (tabId === 'reasoning') tabElements[1].classList.add('active');
            if (tabId === 'telemetry') tabElements[2].classList.add('active');

            document.getElementById(`tab-${tabId}`).classList.add('active');
        }

        async function sendMessage() {
            const text = userInput.value.trim();
            if (text === '' || isProcessing) return;

            // Remove welcome if present
            if (welcomeMessage.parentNode) {
                welcomeMessage.parentNode.removeChild(welcomeMessage);
            }

            isProcessing = true;
            userInput.value = '';
            btnSend.disabled = true;

            // Append User Bubble
            appendMessage('user', text);
            messages.push({ role: 'user', content: text });

            // Append Typing Indicator
            const typingRow = appendTypingIndicator();
            chatContainer.scrollTop = chatContainer.scrollHeight;

            // Prepare Request parameters
            const apiKey = cfgApiKey.value.trim();
            if (apiKey) {
                try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch (e) {}
            }
            const reasoningOpt = optReasoning.checked;
            const telemetryOpt = optTelemetry.checked;

            let url = '/api/v1/regenold/eu-ai-act/ask';
            const params = [];
            if (reasoningOpt) params.push('include_reasoning=true');
            if (telemetryOpt) params.push('include_telemetry=true');
            if (params.length > 0) url += '?' + params.join('&');

            try {
                const headers = {
                    'Content-Type': 'application/json'
                };
                if (apiKey) {
                    headers['X-Regenold-Api-Key'] = apiKey;
                }
                const response = await fetch(url, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({
                        messages: messages.map(m => ({ role: m.role, content: m.content }))
                    })
                });

                // Remove typing indicator
                typingRow.parentNode.removeChild(typingRow);

                if (response.ok) {
                    const data = await response.json();

                    // Render response
                    appendMessage('assistant', data.answer);
                    messages.push({ role: 'assistant', content: data.answer });

                    // Update diagnostics panel
                    updateDiagnostics(data);
                } else {
                    let errMessage = 'Internal Server Error';
                    try {
                        const errData = await response.json();
                        errMessage = errData.detail?.message || errData.detail || response.statusText;
                    } catch (e) {}
                    appendMessage('assistant', `⚠️ **Error ${response.status}**: ${errMessage}\\n\\nPlease verify your local backend configuration and ensure uvicorn is running.`);
                }
            } catch (e) {
                if (typingRow.parentNode) typingRow.parentNode.removeChild(typingRow);
                appendMessage('assistant', `❌ **Connection Failed**: Unable to communicate with the FastAPI backend. Check that the service is running locally.\\n\\n*Detail: ${e.message}*`);
            } finally {
                isProcessing = false;
                userInput.focus();
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }

        function appendMessage(role, text) {
            const row = document.createElement('div');
            row.className = `message-row ${role}-row`;

            // Avatar
            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            if (role === 'user') {
                avatar.innerHTML = '<i data-lucide="user" style="width: 20px; height: 20px; margin: 7px; color: var(--text-secondary);"></i>';
            } else {
                avatar.innerHTML = '<img src="/lexy_avatar.png" alt="Lexy">';
            }

            const bubbleContainer = document.createElement('div');
            bubbleContainer.className = 'msg-bubble-container';

            const bubble = document.createElement('div');
            bubble.className = 'msg-bubble';
            bubble.innerHTML = renderMarkdown(text);  // R104 — sanitized markdown

            const meta = document.createElement('div');
            meta.className = 'msg-meta';
            const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            meta.innerHTML = `<span>${role === 'user' ? 'You' : 'Lexy'}</span> &bull; <span>${timeStr}</span>`;

            bubbleContainer.appendChild(bubble);
            bubbleContainer.appendChild(meta);
            row.appendChild(avatar);
            row.appendChild(bubbleContainer);
            chatContainer.appendChild(row);

            // Re-render Lucide icons
            lucide.createIcons();
        }

        function appendTypingIndicator() {
            const row = document.createElement('div');
            row.className = 'message-row assistant-row';

            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            avatar.innerHTML = '<img src="/lexy_avatar.png" alt="Lexy">';

            const bubbleContainer = document.createElement('div');
            bubbleContainer.className = 'msg-bubble-container';

            const bubble = document.createElement('div');
            bubble.className = 'msg-bubble';

            const typing = document.createElement('div');
            typing.className = 'typing-indicator';
            typing.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';

            bubble.appendChild(typing);
            bubbleContainer.appendChild(bubble);
            row.appendChild(avatar);
            row.appendChild(bubbleContainer);
            chatContainer.appendChild(row);
            return row;
        }

        function updateDiagnostics(data) {
            // Update Citations Tab
            const citationsContainer = document.getElementById('citations-container');
            if (data.references && data.references.length > 0) {
                citationsContainer.innerHTML = '';
                data.references.forEach(ref => {
                    // Extract base article for summary lookup
                    const baseArticleMatch = ref.match(/^(Article \\d+|Annex [IVXLC]+)/);
                    const baseArticle = baseArticleMatch ? baseArticleMatch[1] : null;
                    const description = (baseArticle && articlesSummary[baseArticle]) || "Official reference citation. Grounding logic extracted from the compliance database.";

                    const card = document.createElement('div');
                    card.className = 'ref-card';
                    card.innerHTML = `
                        <div class="ref-header">
                            <span class="ref-title">${escapeHtml(ref)}</span>
                            <span class="ref-badge">Grounded</span>
                        </div>
                        <div class="ref-desc">${escapeHtml(description)}</div>
                    `;
                    citationsContainer.appendChild(card);
                });
            } else {
                citationsContainer.innerHTML = `
                    <p style="color: var(--text-muted); font-size: 13px; text-align: center; margin-top: 40px;">
                        No citations returned for this response.
                    </p>`;
            }

            // Update Telemetry Tab
            const confidenceVal = data.confidence !== undefined && data.confidence !== null ? data.confidence : null;
            if (confidenceVal !== null) {
                document.getElementById('stat-confidence').innerText = confidenceVal.toFixed(2);
                document.getElementById('gauge-confidence').style.width = `${confidenceVal * 100}%`;
            } else {
                document.getElementById('stat-confidence').innerText = 'N/A';
                document.getElementById('gauge-confidence').style.width = '0%';
            }

            document.getElementById('stat-path').innerText = data.retrieval_path || 'N/A';
            document.getElementById('stat-nodes').innerText = data.nodes_traversed !== null && data.nodes_traversed !== undefined ? data.nodes_traversed : 'N/A';
            document.getElementById('stat-kb').innerText = data.kb_version || 'N/A';
            document.getElementById('stat-obligations').innerText = data.obligations_found !== null && data.obligations_found !== undefined ? data.obligations_found : 'N/A';
            document.getElementById('stat-gaps').innerText = data.gaps_found !== null && data.gaps_found !== undefined ? data.gaps_found : 'N/A';

            // Update Reasoning Tab
            const reasoningContainer = document.getElementById('reasoning-container');
            if (data.reasoning) {
                try {
                    // Try parsing as JSON to display in a clean structure
                    const parsed = JSON.parse(data.reasoning);
                    reasoningContainer.innerText = JSON.stringify(parsed, null, 2);
                } catch (e) {
                    reasoningContainer.innerText = data.reasoning;
                }
            } else {
                reasoningContainer.innerText = 'No detailed reasoning logs returned. Ensure "Include Reasoning Trace" option is enabled in the sidebar.';
            }
        }
    </script>
</body>
</html>
"""

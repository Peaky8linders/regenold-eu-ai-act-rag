from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

logger = logging.getLogger(__name__)

def register_web_routes(app: FastAPI) -> None:
    """Mounts the interactive Lexy chat UI + avatar routes.

    The chat UI now lives at ``/app`` (the sign-up funnel owns ``/`` —
    see :func:`app.funnel_ui.register_funnel_routes`). After a sign-up /
    sign-in the funnel redirects to ``/app#key=<lexy_sk_...>``; the chat
    reads the key from the URL fragment (never sent to the server) into
    ``localStorage['regenold_api_key']`` and strips the URL.
    """

    # Absolute path to the lexy_avatar.png image in the workspace root
    avatar_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lexy_avatar.png"))

    @app.get("/app", response_class=HTMLResponse)
    def read_web_ui() -> str:
        # SECURITY: never inject the partner API key into the served HTML.
        # This page is reachable unauthenticated on the public endpoint, so
        # baking ``P2P_REGENOLD_API_KEY`` into the markup would leak it to
        # every visitor. The user's own funnel-issued key arrives via the
        # ``#key=`` URL fragment (or is pasted into the config field) and is
        # persisted client-side in localStorage; the browser sends it as the
        # ``X-Regenold-Api-Key`` header on the same-origin ``/api/v1`` call.
        # The template ships with an EMPTY key field.
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
    <title>Lexy · Compliance Assistant</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    <!-- Marked.js for Markdown parsing -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <!-- DOMPurify — sanitize model/user markdown before innerHTML (XSS guard, R104) -->
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.7/dist/purify.min.js"></script>
    <style>
        :root {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-glass: #ffffff;
            --bg-glass-hover: #ffffff;
            --accent-cyan: #0ea5e9;
            --accent-cyan-rgb: 14, 165, 233;
            --accent-blue: #3b82f6;
            --accent-glow: rgba(14, 165, 233, 0.18);
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border-glass: #e2e8f0;
            --border-glow: rgba(14, 165, 233, 0.35);
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
                radial-gradient(circle at 0% 0%, rgba(14, 165, 233, 0.06) 0%, transparent 40%),
                radial-gradient(circle at 100% 100%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 50% 50%, #f1f5f9 0%, #f8fafc 100%);
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
            background: rgba(15, 23, 42, 0.01);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(15, 23, 42, 0.1);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(14, 165, 233, 0.3);
        }

        /* Layout */
        .sidebar {
            width: var(--sidebar-width);
            background: rgba(255, 255, 255, 0.8);
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
            background: rgba(255, 255, 255, 0.85);
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
            font-family: 'Instrument Serif', Georgia, serif;
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: linear-gradient(135deg, #0f172a 0%, #0ea5e9 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .logo-badge {
            background: rgba(14, 165, 233, 0.1);
            border: 1px solid rgba(14, 165, 233, 0.3);
            color: var(--accent-cyan);
            font-size: 10px;
            font-family: 'Inter', sans-serif;
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
            background: radial-gradient(circle, rgba(14, 165, 233, 0.22) 0%, transparent 70%);
            z-index: -1;
            animation: pulse-glow 3s infinite ease-in-out;
        }

        .avatar-img {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            border: 2px solid var(--accent-cyan);
            object-fit: cover;
            box-shadow: 0 0 20px rgba(14, 165, 233, 0.2);
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
            font-family: 'Instrument Serif', Georgia, serif;
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
            font-family: 'Inter', sans-serif;
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
            background: rgba(15, 23, 42, 0.02);
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
            background: rgba(15, 23, 42, 0.04);
            border-color: rgba(14, 165, 233, 0.15);
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
            background: rgba(14, 165, 233, 0.1);
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid rgba(14, 165, 233, 0.2);
            font-size: 10px;
            font-weight: 600;
            animation: pulse-glow 1.5s infinite ease-in-out;
        }

        /* Config Widget */
        .config-panel {
            background: rgba(15, 23, 42, 0.02);
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
            background: rgba(255, 255, 255, 0.7);
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
            box-shadow: 0 0 10px rgba(14, 165, 233, 0.15);
        }

        .checkbox-input {
            appearance: none;
            width: 16px;
            height: 16px;
            border: 1px solid var(--border-glass);
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.7);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition-speed);
        }

        .checkbox-input:checked {
            border-color: var(--accent-cyan);
            background: rgba(14, 165, 233, 0.15);
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
            background: rgba(255, 255, 255, 0.5);
            backdrop-filter: blur(10px);
        }

        .workspace-title-block {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .workspace-title {
            font-family: 'Inter', sans-serif;
            font-size: 16px;
            font-weight: 600;
        }

        .workspace-actions {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .btn-action {
            background: rgba(15, 23, 42, 0.04);
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
            background: rgba(14, 165, 233, 0.08);
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
            box-shadow: 0 0 10px rgba(14, 165, 233, 0.1);
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
            box-shadow: 0 0 8px rgba(14, 165, 233, 0.2);
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
            background: #e0f2fe;
            border: 1px solid var(--border-glass);
            border-bottom-right-radius: 2px;
            color: var(--text-primary);
        }

        .assistant-row .msg-bubble {
            background: rgba(255, 255, 255, 0.65);
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
            background: rgba(15, 23, 42, 0.05);
            padding: 2px 4px;
            border-radius: 4px;
            color: #f43f5e;
        }

        .cite-badge {
            display: inline-block;
            background: rgba(14, 165, 233, 0.15);
            color: var(--accent-cyan);
            border: 1px solid rgba(14, 165, 233, 0.3);
            border-radius: 6px;
            padding: 1px 6px;
            font-size: 12px;
            font-weight: 500;
            margin: 0 2px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .cite-badge:hover {
            background: rgba(14, 165, 233, 0.25);
            border-color: rgba(14, 165, 233, 0.5);
            box-shadow: 0 0 8px rgba(14, 165, 233, 0.2);
        }

        /* Welcome layout */
        .welcome-container {
            max-width: 680px;
            margin: 15px auto auto auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            padding: 10px 20px 30px 20px;
        }

        .welcome-icon {
            font-size: 40px;
            margin-bottom: 20px;
            animation: float 4s infinite ease-in-out;
        }

        .welcome-title {
            font-family: 'Instrument Serif', Georgia, serif;
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 12px;
            background: linear-gradient(120deg, #0f172a 0%, #0369a1 100%);
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
            background: rgba(255, 255, 255, 0.45);
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
            background: rgba(255, 255, 255, 0.6);
            border-color: var(--accent-cyan);
            box-shadow: 0 0 15px rgba(14, 165, 233, 0.1);
            transform: translateY(-2px);
        }

        .sug-title {
            font-family: 'Inter', sans-serif;
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
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
        }

        .input-wrapper {
            position: relative;
            max-width: 800px;
            margin: auto;
            display: flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.8);
            border: 1px solid var(--border-glass);
            border-radius: 14px;
            padding: 6px 6px 6px 16px;
            transition: var(--transition-speed);
        }

        .input-wrapper:focus-within {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 20px rgba(14, 165, 233, 0.15);
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
            color: #fff;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: var(--transition-speed);
            box-shadow: 0 0 15px rgba(14, 165, 233, 0.3);
            outline: none;
        }

        .btn-send:hover {
            box-shadow: 0 0 25px rgba(14, 165, 233, 0.5);
            transform: scale(1.05);
        }

        .btn-send:disabled {
            background: rgba(15, 23, 42, 0.05);
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
            font-family: 'Inter', sans-serif;
            font-size: 15px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .drawer-tabs {
            display: flex;
            border-bottom: 1px solid var(--border-glass);
            background: rgba(255, 255, 255, 0.3);
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
            background: rgba(15, 23, 42, 0.01);
        }

        .drawer-tab.active {
            color: var(--accent-cyan);
            border-bottom-color: var(--accent-cyan);
            background: rgba(14, 165, 233, 0.02);
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
            background: rgba(15, 23, 42, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            padding: 14px;
            transition: var(--transition-speed);
        }

        .ref-card:hover {
            border-color: rgba(14, 165, 233, 0.15);
            background: rgba(15, 23, 42, 0.03);
        }

        .ref-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .ref-title {
            font-family: 'Inter', sans-serif;
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

        /* Reasoning tab — rich structured display */
        .reasoning-scroller {
            height: 100%;
            display: flex;
            flex-direction: column;
            gap: 10px;
            overflow-y: auto;
        }

        .reasoning-header-bar {
            background: rgba(14, 165, 233, 0.05);
            border: 1px solid rgba(14, 165, 233, 0.2);
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .reasoning-header-bar .schema-ver {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            color: var(--text-muted);
        }

        .reasoning-model-badge {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 20px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .reasoning-model-badge.sonnet {
            background: rgba(14, 165, 233, 0.1);
            border: 1px solid rgba(14, 165, 233, 0.25);
            color: var(--accent-cyan);
        }

        .reasoning-model-badge.opus {
            background: rgba(251, 191, 36, 0.1);
            border: 1px solid rgba(251, 191, 36, 0.3);
            color: #fbbf24;
        }

        .reasoning-model-badge.groq {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.25);
            color: #10b981;
        }

        .reasoning-model-badge.gemini {
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.25);
            color: #3b82f6;
        }

        .reasoning-section {
            background: rgba(15, 23, 42, 0.02);
            border: 1px solid var(--border-glass);
            border-radius: 8px;
            overflow: hidden;
            flex-shrink: 0;
        }

        .reasoning-section-header {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            font-size: 10px;
            font-family: 'Inter', sans-serif;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px solid var(--border-glass);
        }

        .reasoning-section-header.scope-hdr { color: #34d399; background: rgba(52,211,153,0.05); }
        .reasoning-section-header.intent-hdr { color: #60a5fa; background: rgba(96,165,250,0.05); }
        .reasoning-section-header.retrieval-hdr { color: var(--accent-cyan); background: rgba(14, 165, 233,0.04); }
        .reasoning-section-header.graph-hdr { color: #a78bfa; background: rgba(167,139,250,0.05); }
        .reasoning-section-header.guards-hdr { color: #fb923c; background: rgba(251,146,60,0.05); }
        .reasoning-section-header.model-hdr { color: #c084fc; background: rgba(192,132,252,0.05); }
        .reasoning-section-header.subq-hdr { color: #38bdf8; background: rgba(56,189,248,0.05); }
        .reasoning-section-header.notes-hdr { color: #94a3b8; background: rgba(148,163,184,0.03); }

        .reasoning-section-body {
            padding: 10px 14px;
            font-size: 12px;
            line-height: 1.6;
            color: var(--text-secondary);
        }

        .rlog-kv {
            display: flex;
            gap: 8px;
            margin-bottom: 4px;
            align-items: flex-start;
        }

        .rlog-key {
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            min-width: 90px;
            flex-shrink: 0;
            padding-top: 1px;
        }

        .rlog-val {
            color: var(--text-secondary);
            font-size: 12px;
            word-break: break-word;
        }

        .rlog-val.highlight { color: var(--text-primary); }
        .rlog-val.ok { color: #34d399; }
        .rlog-val.warn { color: #fbbf24; }

        .rlog-tag {
            display: inline-block;
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-family: 'JetBrains Mono', monospace;
            margin: 1px 3px 1px 0;
            background: rgba(15, 23, 42, 0.05);
            border: 1px solid var(--border-glass);
            color: var(--text-secondary);
        }

        .rlog-subq-card {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 6px;
            padding: 8px 10px;
            margin-bottom: 8px;
            border-left: 2px solid rgba(56, 189, 248, 0.4);
        }

        .rlog-subq-card:last-child { margin-bottom: 0; }

        .rlog-subq-q {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: #38bdf8;
            margin-bottom: 6px;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .rlog-note-line {
            font-size: 11px;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-secondary);
            padding: 3px 0;
            border-bottom: 1px solid rgba(15, 23, 42,0.03);
            word-break: break-word;
            white-space: pre-wrap;
        }

        .rlog-note-line:last-child { border-bottom: none; }

        .rlog-empty {
            color: var(--text-muted);
            font-size: 13px;
            text-align: center;
            margin-top: 40px;
        }

        .reasoning-log-container {
            display: none; /* kept for backward compat but hidden */
        }

        /* Stats tab */
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .stat-card {
            background: rgba(15, 23, 42, 0.02);
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
            font-family: 'Inter', sans-serif;
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-value.highlight {
            color: var(--accent-cyan);
            text-shadow: 0 0 10px rgba(14, 165, 233, 0.2);
        }

        .progress-bar-bg {
            background: rgba(15, 23, 42, 0.05);
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

        /* Thinking pipeline — animated answer-path progress (ChatGPT / Gemini style).
           Each stage is revealed in turn, held >= 1s, with a shimmering active
           label and a checkmark on completion. */
        .thinking-panel {
            display: flex;
            flex-direction: column;
            min-width: 250px;
        }

        .thinking-head {
            display: flex;
            align-items: center;
            gap: 9px;
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            letter-spacing: 0.3px;
            margin-bottom: 12px;
        }

        .think-steps {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }

        .think-step {
            display: flex;
            align-items: center;
            gap: 11px;
            padding: 4px 0;
            font-size: 13px;
            opacity: 0;
            transform: translateY(5px);
            transition: opacity 0.4s ease, transform 0.4s ease;
        }

        .think-step.visible {
            opacity: 1;
            transform: none;
        }

        .think-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--accent-cyan);
        }

        .thinking-panel .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--text-muted);
        }

        .thinking-panel .ring,
        .thinking-head .head-ring {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid rgba(14, 165, 233, 0.18);
            border-top-color: var(--accent-cyan);
            animation: spin 0.7s linear infinite;
        }

        .thinking-head .head-ring {
            width: 13px;
            height: 13px;
            flex-shrink: 0;
        }

        .think-icon .check {
            width: 15px;
            height: 15px;
        }

        .think-label {
            color: var(--text-secondary);
            transition: color 0.3s;
        }

        .think-step.done .think-label {
            color: var(--text-muted);
        }

        .think-step.active .think-label {
            background: linear-gradient(90deg, var(--text-muted) 0%, #f8fafc 30%, var(--accent-cyan) 50%, #f8fafc 70%, var(--text-muted) 100%);
            background-size: 200% auto;
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: shimmer 1.5s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        @keyframes shimmer {
            to { background-position: -200% center; }
        }

        /* Animations */
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
                <h1 class="welcome-title">EU AI Act Workspace</h1>
                <p class="welcome-desc">
                    I am Lexy, your EU AI Act compliance assistant. Ask a question and I will answer with citations to the exact Articles and Annexes.
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
                <div class="reasoning-scroller" id="reasoning-container">
                    <p class="rlog-empty">No reasoning trace captured. Enable "Include Reasoning Trace" before sending.</p>
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
            let safeHtml = window.DOMPurify ? DOMPurify.sanitize(raw) : escapeHtml(text || '');
            
            // Post-process to render citations as interactive badges
            // Match exactly Article N or Annex X with word boundaries
            safeHtml = safeHtml.replace(/\b(Article\s+[0-9]+(?:\.[0-9a-zA-Z]+)?|Annex\s+[IVXLCDM]+(?:\.[0-9a-zA-Z]+)?)\b/gi, '<span class="cite-badge">$1</span>');
            return safeHtml;
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
                    document.getElementById('diag-api').innerHTML = `<span class="badge-ok">OK (v${escapeHtml(data.version || '1.0.0')})</span>`;
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
            document.getElementById('reasoning-container').innerHTML = '<p class="rlog-empty">No reasoning trace captured. Enable "Include Reasoning Trace" before sending.</p>';
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

            // Show the animated "thinking" pipeline — a visualisation of the
            // real answer path (input -> scope -> classify -> retrieve -> graph
            // -> ground -> synthesise -> polish -> output). Each stage is held
            // for at least one second so the journey is legible, ChatGPT /
            // Gemini "thinking" style. The request fires in parallel below.
            const pipeline = appendThinkingPipeline();
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

            const headers = { 'Content-Type': 'application/json' };
            if (apiKey) {
                headers['X-Regenold-Api-Key'] = apiKey;
            }

            // Fire the request in parallel with the animation. ``settled`` never
            // rejects — it resolves once the request has settled (success OR
            // failure) so the pipeline knows when the answer is ready and the
            // final "Polishing" stage can complete.
            const fetchPromise = fetch(url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    messages: messages.map(m => ({ role: m.role, content: m.content }))
                })
            });
            const settled = fetchPromise.then(
                (r) => ({ ok: true, response: r }),
                (e) => ({ ok: false, error: e })
            );

            try {
                // Play the full path: resolves after every stage has shown
                // (>= 1s each) AND the response has arrived.
                await pipeline.run(settled);
                pipeline.remove();

                const outcome = await settled;
                if (!outcome.ok) {
                    appendMessage('assistant', `❌ **Connection Failed**: Unable to communicate with the FastAPI backend. Check that the service is running locally.\\n\\n*Detail: ${outcome.error.message}*`);
                } else {
                    const response = outcome.response;
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
                }
            } catch (e) {
                pipeline.remove();
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

        // PIPELINE_STEPS — the human-readable stages of the real answer path
        // the backend walks for every question: flatten history + parse the
        // question (input) -> scope / jurisdiction gate -> deterministic risk
        // & role classification -> BM25 + KB retrieval -> Neo4j knowledge-graph
        // expansion -> citation grounding -> Stage-2 LLM synthesis -> normalise
        // + tone (polish) -> output. Rendered ChatGPT / Gemini "thinking"
        // style, each stage visible for at least one second.
        const PIPELINE_STEPS = [
            'Reading your question',
            'Checking scope & jurisdiction',
            'Classifying risk & role',
            'Searching the EU AI Act',
            'Traversing the knowledge graph',
            'Grounding citations',
            'Synthesising the answer',
            'Polishing & formatting'
        ];

        // Minimum on-screen time per stage. The spec requires >= 1 second;
        // 1100ms lets the shimmer read as deliberate rather than a flicker.
        const PIPELINE_STEP_MS = 1100;

        // Inline SVG checkmark (no Lucide re-render needed mid-animation).
        // Uses currentColor so the active accent (cyan) flows through.
        const _CHECK_SVG = '<svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

        // Build the animated "thinking" pipeline that replaces the plain typing
        // dots. Returns a controller: ``run(donePromise)`` plays each stage in
        // turn (>= PIPELINE_STEP_MS each) and holds on the final "Polishing"
        // stage until ``donePromise`` settles, so slow Stage-2 LLM requests keep
        // the panel spinning; ``remove()`` tears the row down.
        function appendThinkingPipeline() {
            const row = document.createElement('div');
            row.className = 'message-row assistant-row';

            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            avatar.innerHTML = '<img src="/lexy_avatar.png" alt="Lexy">';

            const bubbleContainer = document.createElement('div');
            bubbleContainer.className = 'msg-bubble-container';

            const bubble = document.createElement('div');
            bubble.className = 'msg-bubble';

            const panel = document.createElement('div');
            panel.className = 'thinking-panel';

            const head = document.createElement('div');
            head.className = 'thinking-head';
            head.innerHTML = '<span class="head-ring"></span><span>Reasoning over the EU AI Act…</span>';

            const stepsWrap = document.createElement('div');
            stepsWrap.className = 'think-steps';

            const stepEls = PIPELINE_STEPS.map((label) => {
                const el = document.createElement('div');
                el.className = 'think-step';
                el.innerHTML = '<span class="think-icon"><span class="dot"></span></span>'
                    + '<span class="think-label">' + escapeHtml(label) + '</span>';
                stepsWrap.appendChild(el);
                return el;
            });

            panel.appendChild(head);
            panel.appendChild(stepsWrap);
            bubble.appendChild(panel);
            bubbleContainer.appendChild(bubble);
            row.appendChild(avatar);
            row.appendChild(bubbleContainer);
            chatContainer.appendChild(row);

            const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

            function setState(el, state) {
                el.classList.add('visible');
                el.classList.remove('active', 'done');
                const icon = el.querySelector('.think-icon');
                if (state === 'active') {
                    el.classList.add('active');
                    icon.innerHTML = '<span class="ring"></span>';
                } else if (state === 'done') {
                    el.classList.add('done');
                    icon.innerHTML = _CHECK_SVG;
                }
            }

            async function run(donePromise) {
                let answered = false;
                Promise.resolve(donePromise).then(() => { answered = true; }, () => { answered = true; });
                for (let i = 0; i < stepEls.length; i++) {
                    setState(stepEls[i], 'active');
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                    await sleep(PIPELINE_STEP_MS);
                    // Hold the final "Polishing" stage until the answer lands so
                    // the panel keeps spinning through slow Stage-2 LLM requests
                    // instead of stalling on a finished checklist.
                    if (i === stepEls.length - 1) {
                        while (!answered) { await sleep(120); }
                    }
                    setState(stepEls[i], 'done');
                }
            }

            function remove() {
                if (row.parentNode) row.parentNode.removeChild(row);
            }

            return { row, run, remove };
        }

        // ── renderReasoningLog ─────────────────────────────────────────────
        // Builds a rich structured display from the JSON reasoning trace payload.
        // Each field gets a dedicated colour-coded section card; notes are shown
        // in full (no truncation) as a timeline log.
        function renderReasoningLog(container, rawReasoning) {
            if (!rawReasoning) {
                container.innerHTML = '<p class="rlog-empty">No detailed reasoning logs returned. Enable "Include Reasoning Trace" in the sidebar.</p>';
                return;
            }

            let trace;
            try { trace = JSON.parse(rawReasoning); }
            catch (e) {
                container.innerHTML = '<p class="rlog-empty">Reasoning payload is not valid JSON.</p>';
                return;
            }

            // Detect which Stage-2 model was used from the notes array.
            // The engine records e.g. "stage2_model=claude-opus-4-8 complex=true"
            // or "stage2_model=claude-sonnet-4-6 complex=false" in notes.
            let detectedModel = '';
            let isComplex = false;
            (trace.notes || []).forEach(n => {
                const m = n.match(/stage2_model[=:]\s*(\S+)/i);
                if (m) detectedModel = m[1];
                if (/complex[=:]?\s*true/i.test(n)) isComplex = true;
            });
            // Also check stage2_polish landed + complex inference from guards/notes
            if (!detectedModel && trace.stage2_polish) {
                // Fall back to reading the note that records which model was used
                (trace.notes || []).forEach(n => {
                    if (/opus.?4/i.test(n)) detectedModel = 'claude-opus-4';
                    else if (/sonnet/i.test(n)) detectedModel = 'claude-sonnet-4-6';
                    else if (/groq|llama/i.test(n)) detectedModel = 'groq-llama';
                });
            }
            if (!detectedModel && trace.stage2_polish === true) detectedModel = 'claude-opus-4-8'; // default
            if (!detectedModel && trace.stage2_polish === false) detectedModel = 'claude-sonnet-4-6';

            function modelClass(m) {
                if (!m) return 'sonnet';
                if (/opus/i.test(m)) return 'opus';
                if (/groq|llama/i.test(m)) return 'groq';
                if (/gemini/i.test(m)) return 'gemini';
                return 'sonnet';
            }

            function modelLabel(m) {
                if (!m) return 'Sonnet 4.6';
                if (/opus.*4.*8/i.test(m)) return '★ Opus 4.8';
                if (/opus/i.test(m)) return '★ Opus';
                if (/groq|llama/i.test(m)) return '⚡ Groq Llama';
                if (/gemini/i.test(m)) return '✨ Gemini 3.1';
                return 'Sonnet 4.6';
            }

            function section(hdrClass, icon, title, bodyHTML) {
                return `<div class="reasoning-section">
                    <div class="reasoning-section-header ${hdrClass}">${icon} ${escapeHtml(title)}</div>
                    <div class="reasoning-section-body">${bodyHTML}</div>
                </div>`;
            }

            function kv(key, valHTML) {
                return `<div class="rlog-kv"><span class="rlog-key">${escapeHtml(key)}</span><span class="rlog-val">${valHTML}</span></div>`;
            }

            function tags(arr) {
                return (arr || []).map(t => `<span class="rlog-tag">${escapeHtml(t)}</span>`).join('');
            }

            const parts = [];

            // ── Header bar ───────────────────────────────────────────────────
            const schemaVer = trace.schema_version || '?';
            const mClass = modelClass(detectedModel);
            const mLabel = modelLabel(detectedModel);
            const complexBadge = isComplex ? ' <span style="font-size:10px;color:#a78bfa">(complex routing)</span>' : '';
            // An LLM model only PRODUCED this answer when Stage-2 actually landed
            // (trace.stage2_polish === true). The "stage2_model=…" note records the
            // model the engine *selected/attempted* BEFORE the call — so when Stage-2
            // fails (provider down / wrapper outage / truncation) the deterministic
            // pipeline produced the answer. Pre-R141 the header always showed the
            // attempted model, so an outage read as "★ Opus 4.8 answered" when Opus
            // never ran. Show the honest answer source instead.
            const stage2Landed = trace.stage2_polish === true;
            let answerBadge;
            if (stage2Landed) {
                answerBadge = `<span class="reasoning-model-badge ${mClass}">${escapeHtml(mLabel)}${complexBadge}</span>`;
            } else {
                const attempted = (trace.stage2_polish === false && detectedModel)
                    ? ` <span style="font-size:10px;color:var(--text-muted)">(Stage-2 ${escapeHtml(mLabel)} did not land)</span>`
                    : '';
                answerBadge = `<span class="reasoning-model-badge" style="background:#3f3f46;color:#d4d4d8">Deterministic</span>${attempted}`;
            }
            parts.push(`<div class="reasoning-header-bar">
                <span class="schema-ver">schema ${escapeHtml(schemaVer)}</span>
                ${answerBadge}
            </div>`);

            // ── Scope ────────────────────────────────────────────────────────
            if (trace.scope && Object.keys(trace.scope).length > 0) {
                const sc = trace.scope;
                const vclass = sc.verdict === 'in_scope' ? 'ok' : sc.verdict === 'out_of_scope' ? 'warn' : '';
                let body = kv('verdict', `<span class="rlog-val ${vclass} highlight">${escapeHtml(sc.verdict || '—')}</span>`);
                if (sc.evidence) body += kv('evidence', escapeHtml(sc.evidence));
                if (sc.near_oos_framework) body += kv('near-oos', `<span class="rlog-val warn">${escapeHtml(sc.near_oos_framework)}</span>`);
                parts.push(section('scope-hdr', '🔍', 'Scope Gate', body));
            }

            // ── Intent ───────────────────────────────────────────────────────
            if (trace.intent_label || trace.compound_roles?.length || trace.query_denoiser?.fired !== undefined) {
                let body = '';
                if (trace.intent_label) body += kv('intent', `<span class="rlog-val highlight">${escapeHtml(trace.intent_label)}</span>`);
                if (trace.compound_roles?.length) body += kv('roles', tags(trace.compound_roles));
                const qd = trace.query_denoiser;
                if (qd && Object.keys(qd).length) {
                    body += kv('denoiser', `<span class="rlog-val ${qd.fired ? 'ok' : ''}">${qd.fired ? 'fired' : 'skipped'}${qd.fallback_reason ? ' (' + escapeHtml(qd.fallback_reason) + ')' : ''}</span>`);
                    if (qd.rewritten_chars) body += kv('rewritten', escapeHtml(String(qd.rewritten_chars)) + ' chars');
                    if (qd.model) body += kv('model', escapeHtml(qd.model));
                }
                if (body) parts.push(section('intent-hdr', '🎯', 'Intent & Query', body));
            }

            // ── Retrieval ────────────────────────────────────────────────────
            if (trace.retrieval_path || trace.anchors_used?.length || trace.references?.length || trace.top_k_bm25?.length) {
                let body = '';
                if (trace.retrieval_path) body += kv('path', `<span class="rlog-val highlight">${escapeHtml(trace.retrieval_path)}</span>`);
                if (trace.anchors_used?.length) body += kv('anchors', tags(trace.anchors_used));
                // R131 — the FINAL wire citations (Article 26 / Article 3.1 /
                // Annex IV.2 — sub-points included), recorded after every
                // reference pass, so the reasoning log shows the exact refs the
                // answer ships, not just the input anchors.
                if (trace.references?.length) body += kv('citations', tags(trace.references));
                if (trace.xref_expand_added?.length) body += kv('xrefs', tags(trace.xref_expand_added));
                if (trace.top_k_bm25?.length) {
                    const hits = trace.top_k_bm25.map(h => `<span class="rlog-tag">${escapeHtml(h.ref || '')} <span style="color:var(--text-muted)">${h.score != null ? h.score.toFixed(1) : ''}</span></span>`).join('');
                    body += kv('BM25 top-k', hits);
                }
                if (trace.engine_confidence != null) body += kv('confidence', `<span class="rlog-val highlight">${trace.engine_confidence.toFixed(3)}</span>`);
                if (trace.cache_hit != null) body += kv('cache', `<span class="rlog-val ${trace.cache_hit ? 'ok' : ''}">${trace.cache_hit ? 'HIT' : 'miss'}</span>`);
                if (body) parts.push(section('retrieval-hdr', '📚', 'Retrieval', body));
            }

            // ── Graph expansion ──────────────────────────────────────────────
            if (trace.graph_2hop_added?.length) {
                const body = kv('2-hop added', tags(trace.graph_2hop_added));
                parts.push(section('graph-hdr', '🕸', 'Graph Expansion', body));
            }

            // ── Guards fired ─────────────────────────────────────────────────
            if (trace.guards_fired?.length) {
                const body = kv('guards', tags(trace.guards_fired));
                parts.push(section('guards-hdr', '🛡', 'Guards Fired', body));
            }

            // ── Stage-2 model ────────────────────────────────────────────────
            if (trace.stage2_polish !== null && trace.stage2_polish !== undefined) {
                // Distinguish "the LLM was attempted but FAILED" (provider error /
                // wrapper outage / truncation → deterministic fallback) from a plain
                // gate-skip, so a provider outage is VISIBLE here instead of being
                // masked as "Opus 4.8 answered".
                const failNote = (trace.notes || []).find(n => /stage2_failed_both_providers|stage2_call_failed/i.test(n));
                const stage2State = stage2Landed
                    ? 'landed'
                    : (failNote ? 'attempted → FAILED → deterministic fallback' : 'skipped → deterministic');
                let body = kv('stage2', `<span class="rlog-val ${stage2Landed ? 'ok' : 'warn'}">${stage2State}</span>`);
                if (detectedModel) {
                    const lbl = stage2Landed ? 'model used' : 'model attempted';
                    const tail = stage2Landed ? '' : ' <span style="color:var(--text-muted);font-size:10px">— did not produce this answer</span>';
                    body += kv(lbl, `<span class="rlog-val highlight reasoning-model-badge ${mClass}" style="padding:2px 6px;font-size:10px">${escapeHtml(modelLabel(detectedModel))}</span>${tail}`);
                }
                if (failNote) body += kv('failure', `<span class="rlog-val warn">${escapeHtml(failNote)}</span>`);
                if (isComplex) body += kv('gate', '<span class="rlog-val" style="color:#a78bfa">complex routing — question complexity gate fired</span>');
                parts.push(section('model-hdr', '✦', 'LLM Stage-2', body));
            }

            // ── Sub-queries (R110 Sufficient-Context) ────────────────────────
            if (trace.sub_queries?.length) {
                let body = '';
                trace.sub_queries.forEach((sq, i) => {
                    const refs = (sq.refs || []).map(r => `<span class="rlog-tag">${escapeHtml(r)}</span>`).join('');
                    body += `<div class="rlog-subq-card">
                        <div class="rlog-subq-q">[${i+1}] ${escapeHtml(sq.q || '')}</div>
                        ${sq.source ? `<div class="rlog-kv"><span class="rlog-key">source</span><span class="rlog-val">${escapeHtml(sq.source)}</span></div>` : ''}
                        ${sq.reason ? `<div class="rlog-kv"><span class="rlog-key">reason</span><span class="rlog-val">${escapeHtml(sq.reason)}</span></div>` : ''}
                        ${refs ? `<div class="rlog-kv"><span class="rlog-key">refs</span><span class="rlog-val">${refs}</span></div>` : ''}
                    </div>`;
                });
                parts.push(section('subq-hdr', '🔄', `Sub-Queries (${trace.sub_queries.length})`, body));
            }

            // ── Notes timeline ───────────────────────────────────────────────
            if (trace.notes?.length) {
                const lines = trace.notes.map(n => `<div class="rlog-note-line">${escapeHtml(n)}</div>`).join('');
                parts.push(section('notes-hdr', '📝', `Engine Notes (${trace.notes.length})`, lines));
            }

            // ── LLM Thinking ─────────────────────────────────────────────────
            if (trace.llm_thinking) {
                if (typeof trace.llm_thinking === 'string') {
                    const thinkingHtml = `<div class="rlog-note-line" style="white-space: pre-wrap; font-family: monospace; font-size: 0.9em; max-height: 400px; overflow-y: auto;">${escapeHtml(trace.llm_thinking)}</div>`;
                    parts.push(section('model-hdr', '🧠', 'LLM Thinking', thinkingHtml));
                } else {
                    for (const [stage, text] of Object.entries(trace.llm_thinking)) {
                        const thinkingHtml = `<div class="rlog-note-line" style="white-space: pre-wrap; font-family: monospace; font-size: 0.9em; max-height: 400px; overflow-y: auto;">${escapeHtml(text)}</div>`;
                        parts.push(section('model-hdr-' + stage.replace(/\\s+/g, '-'), '🧠', `LLM Thinking (${stage})`, thinkingHtml));
                    }
                }
            }

            if (parts.length === 0) {
                container.innerHTML = '<p class="rlog-empty">Trace received but contains no structured fields.</p>';
            } else {
                container.innerHTML = parts.join('');
            }
            // Switch to Reasoning tab automatically so the user sees it
            switchTab('reasoning');
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

            // Update Reasoning Tab — rich structured renderer
            renderReasoningLog(document.getElementById('reasoning-container'), data.reasoning);
        }
    </script>
</body>
</html>
"""

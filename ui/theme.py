"""
Dynamic Theme Manager for P2P Collaboration System.
Provides 4 time-of-day adaptive color schemes plus modern Olive and Dark themes.
"""
from datetime import datetime

THEMES = {
    'morning': {
        'name': 'Morning Glow',
        'bg': '#FEF9C3',
        'primary': '#EAB308',
        'secondary': '#3B82F6',
        'accent': '#2DD4BF',
        'text': '#1F2937',
        'panel_bg': '#FFFFFF',
        'input_bg': '#FFFBEB',
        'border': '#FCD34D',
        'btn_text': '#FFFFFF',
        'badge_bg': '#FEF08A'
    },
    'daytime': {
        'name': 'Daytime Crisp',
        'bg': '#F8FAFC',
        'primary': '#0284C7',
        'secondary': '#10B981',
        'accent': '#6366F1',
        'text': '#0F172A',
        'panel_bg': '#FFFFFF',
        'input_bg': '#F1F5F9',
        'border': '#CBD5E1',
        'btn_text': '#FFFFFF',
        'badge_bg': '#E2E8F0'
    },
    'evening': {
        'name': 'Sunset Amber',
        'bg': '#FFEDD5',
        'primary': '#EA580C',
        'secondary': '#E11D48',
        'accent': '#2563EB',
        'text': '#1E293B',
        'panel_bg': '#FFF7ED',
        'input_bg': '#FED7AA',
        'border': '#FB923C',
        'btn_text': '#FFFFFF',
        'badge_bg': '#FFEDD5'
    },
    'night': {
        'name': 'Midnight Cyber',
        'bg': '#0F172A',
        'primary': '#8B5CF6',
        'secondary': '#06B6D4',
        'accent': '#F59E0B',
        'text': '#F1F5F9',
        'panel_bg': '#1E293B',
        'input_bg': '#334155',
        'border': '#475569',
        'btn_text': '#FFFFFF',
        'badge_bg': '#334155'
    },
    'olive': {
        'name': 'Olive Minimal',
        'bg': '#F3F4F2',
        'primary': '#556B2F',
        'secondary': '#7A9A48',
        'accent': '#B7C4A8',
        'text': '#2D3748',
        'panel_bg': '#FFFFFF',
        'input_bg': '#F7F8F6',
        'border': '#CBD5C0',
        'btn_text': '#FFFFFF',
        'badge_bg': '#E5EADF'
    }
}


class ThemeManager:
    """Manages application theming, time-based resolution, and theme switching."""

    @staticmethod
    def get_time_adaptive_theme() -> dict:
        """Pick theme based on local time of day."""
        hour = datetime.now().hour
        if 6 <= hour < 11:
            return THEMES['morning']
        elif 11 <= hour < 17:
            return THEMES['daytime']
        elif 17 <= hour < 20:
            return THEMES['evening']
        else:
            return THEMES['night']

    @staticmethod
    def get_login_theme() -> dict:
        """Clean olive card theme for startup."""
        return THEMES['olive']

    @staticmethod
    def get_theme_by_name(name: str) -> dict:
        """Get theme by specific key."""
        return THEMES.get(name.lower(), THEMES['night'])

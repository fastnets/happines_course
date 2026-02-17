def set_screen(context, screen: str):
    context.user_data["screen"] = screen

def get_screen(context):
    return context.user_data.get("screen", "main")

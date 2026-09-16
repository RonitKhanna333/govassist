"""The few things the helper says that aren't derived from a rule or clause.

Static and hand-translated, like the question bank, because they never
change and translating them per turn would add latency and a model call to a
greeting. They carry no facts about the scheme -- anything factual comes from
clauses, through the verifier.
"""

from __future__ import annotations

PHRASES: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Namaste! I'll ask you a few simple questions to see if this scheme "
              "can help you. You can also ask me anything about it.",
        "hi": "नमस्ते! मैं आपसे कुछ आसान सवाल पूछूँगा ताकि पता चले कि यह योजना "
              "आपकी मदद कर सकती है या नहीं। आप इसके बारे में मुझसे कुछ भी पूछ सकते हैं।",
        "pa": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਤੁਹਾਨੂੰ ਕੁਝ ਸੌਖੇ ਸਵਾਲ ਪੁੱਛਾਂਗਾ ਤਾਂ ਜੋ ਪਤਾ ਲੱਗੇ ਕਿ "
              "ਇਹ ਸਕੀਮ ਤੁਹਾਡੀ ਮਦਦ ਕਰ ਸਕਦੀ ਹੈ ਜਾਂ ਨਹੀਂ। ਤੁਸੀਂ ਇਸ ਬਾਰੇ ਮੈਨੂੰ ਕੁਝ ਵੀ ਪੁੱਛ ਸਕਦੇ ਹੋ।",
        "ta": "வணக்கம்! இந்தத் திட்டம் உங்களுக்கு உதவுமா என்று பார்க்க சில எளிய "
              "கேள்விகள் கேட்கிறேன். இதைப் பற்றி நீங்கள் எதையும் என்னிடம் கேட்கலாம்.",
    },
    "ack": {
        "en": "Got it.", "hi": "ठीक है।", "pa": "ਠੀਕ ਹੈ।", "ta": "சரி.",
    },
    "unknown": {
        "en": "I don't have that information for this scheme. Your block or district "
              "office can tell you, or you can check the scheme's official website.",
        "hi": "इस योजना के बारे में यह जानकारी मेरे पास नहीं है। आपका ब्लॉक या ज़िला "
              "दफ़्तर इसमें मदद कर सकता है, या आप योजना की सरकारी वेबसाइट देख सकते हैं।",
        "pa": "ਇਸ ਸਕੀਮ ਬਾਰੇ ਇਹ ਜਾਣਕਾਰੀ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ। ਤੁਹਾਡਾ ਬਲਾਕ ਜਾਂ ਜ਼ਿਲ੍ਹਾ "
              "ਦਫ਼ਤਰ ਇਸ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹੈ, ਜਾਂ ਤੁਸੀਂ ਸਕੀਮ ਦੀ ਸਰਕਾਰੀ ਵੈੱਬਸਾਈਟ ਵੇਖ ਸਕਦੇ ਹੋ।",
        "ta": "இந்தத் திட்டத்தைப் பற்றி இந்தத் தகவல் என்னிடம் இல்லை. உங்கள் வட்டார "
              "அல்லது மாவட்ட அலுவலகம் உதவலாம், அல்லது திட்டத்தின் அரசு இணையதளத்தைப் பார்க்கலாம்.",
    },
    "not_understood": {
        "en": "Sorry, I didn't catch that. Please answer again, or use the buttons below.",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। कृपया फिर से बताइए, या नीचे दिए बटन दबाइए।",
        "pa": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਸਮਝ ਨਹੀਂ ਸਕਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਫਿਰ ਦੱਸੋ, ਜਾਂ ਹੇਠਾਂ ਦਿੱਤੇ ਬਟਨ ਦਬਾਓ।",
        "ta": "மன்னிக்கவும், எனக்குப் புரியவில்லை. மீண்டும் சொல்லுங்கள், அல்லது கீழே உள்ள பொத்தான்களை அழுத்துங்கள்.",
    },
    "busy": {
        "en": "I'm getting a lot of questions right now. Please wait a moment and "
              "ask again -- your answers so far are saved.",
        "hi": "अभी मेरे पास बहुत सारे सवाल आ रहे हैं। कृपया थोड़ी देर रुककर फिर से "
              "पूछिए -- आपके अब तक के जवाब सुरक्षित हैं।",
        "pa": "ਇਸ ਵੇਲੇ ਮੇਰੇ ਕੋਲ ਬਹੁਤ ਸਾਰੇ ਸਵਾਲ ਆ ਰਹੇ ਹਨ। ਕਿਰਪਾ ਕਰਕੇ ਥੋੜ੍ਹਾ ਰੁਕ ਕੇ ਫਿਰ "
              "ਪੁੱਛੋ -- ਤੁਹਾਡੇ ਹੁਣ ਤੱਕ ਦੇ ਜਵਾਬ ਸੰਭਾਲੇ ਹੋਏ ਹਨ।",
        "ta": "இப்போது எனக்கு நிறைய கேள்விகள் வருகின்றன. சற்று நேரம் கழித்து மீண்டும் "
              "கேளுங்கள் -- இதுவரை நீங்கள் சொன்ன பதில்கள் சேமிக்கப்பட்டுள்ளன.",
    },
    "chat": {
        "en": "Happy to help. Whenever you're ready, let's continue.",
        "hi": "मदद करके खुशी होगी। जब आप तैयार हों, आगे बढ़ते हैं।",
        "pa": "ਮਦਦ ਕਰਕੇ ਖ਼ੁਸ਼ੀ ਹੋਵੇਗੀ। ਜਦੋਂ ਤੁਸੀਂ ਤਿਆਰ ਹੋਵੋ, ਅੱਗੇ ਵਧਦੇ ਹਾਂ।",
        "ta": "உதவுவதில் மகிழ்ச்சி. நீங்கள் தயாரானதும் தொடரலாம்.",
    },
}


def phrase(key: str, locale: str) -> str:
    table = PHRASES[key]
    return table.get(locale) or table["en"]

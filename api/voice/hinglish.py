"""Romanized presentation of the existing general interview, never new rules."""
from __future__ import annotations

# Translations of data/attributes.json questions. Attribute IDs remain unchanged.
QUESTIONS = {
    "age": "Aapki umar kitni hai?",
    "is_indian_citizen": "Kya aap Bharat ke nagrik hain?",
    "has_bank_or_post_office_account": "Kya aapka apna bank ya post office account hai?",
    "has_savings_bank_account": "Kya bank mein aapka savings account hai?",
    "ever_paid_income_tax": "Kya aapne kabhi income tax bhara hai?",
    "paid_income_tax_last_year": "Kya aapne pichhle saal income tax bhara tha?",
    "is_government_employee": "Kya aap sarkari ya public sector ki naukri karte hain, ya usse retire hue hain?",
    "consents_to_auto_debit": "Kya aap bank ko saalana fees apne account se apne aap kaatne ki ijazat denge?",
    "household_is_bpl": "Kya aapka parivaar gareebi rekha se neeche, yani BPL mein hai?",
    "owns_cultivable_land": "Kya aapke naam par kheti ki zameen hai?",
    "land_hectares": "Aapke paas kitne hectare kheti ki zameen hai?",
    "in_other_pension_or_social_security_scheme": "Kya aap pehle se kisi aur pension fund mein hain, jaise NPS, PF ya EPFO, ESIC, PM-SYM ya PM-LVM?",
    "is_institutional_landholder": "Kya zameen kisi vyakti ke bajaay trust, company ya sanstha ke naam par hai?",
    "holds_or_held_public_office": "Kya aap abhi ya pehle kabhi mantri, MP, MLA, mayor ya zila panchayat ke pramukh rahe hain?",
    "is_practising_professional": "Kya aap registered doctor, engineer, lawyer, chartered accountant ya architect ke roop mein kaam karte hain?",
    "is_street_vendor": "Kya aap rozi-roti ke liye sadak, footpath ya bazaar mein saamaan ya services bechte hain?",
    "vends_in_town_or_peri_urban": "Kya aap kasbe, shehar ya uske paas ke ilaake mein bechte hain?",
    "is_existing_micro_food_processing_unit": "Kya aap pehle se bechne ke liye khaane ki cheezein banaate, process ya pack karte hain?",
    "applicant_type": "Kya aap apne business ke liye akele apply kar rahe hain?",
    "identified_in_slup_or_verified": "Kya kisi sarkari officer ne aapke business ka daura karke use zila list mein joda hai?",
    "is_unincorporated": "Kya aap business khud ya parivaar ke saath chalaate hain, registered company ke roop mein nahi?",
    "worker_count": "Aapke business mein kitne log kaam karte hain?",
    "has_enterprise_ownership_right": "Kya business aapka hai?",
    "passed_class_8": "Kya aapne class 8 tak ya usse aage padhaai ki hai?",
    "family_member_already_received_assistance": "Kya aapke parivaar mein kisi ne is scheme se pehle hi paise liye hain?",
    "will_formalize": "Kya aap apne business ko officially register karne ke liye taiyaar hain?",
    "own_contribution_percent": "Kul kharche ka kitna hissa aap khud de sakte hain?",
    "will_take_bank_loan": "Kya baaki kharche ke liye aap bank loan lene ko taiyaar hain?",
    "is_woman": "Kya apply karne waali vyakti mahila hain?",
    "household_has_lpg_or_png": "Kya aapke ghar mein kisi ke paas pehle se gas cylinder connection ya piped gas hai?",
    "will_give_deprivation_declaration": "Kya aap apne parivaar ke gareeb hone ka form bharenge aur officials ko uski jaanch karne denge?",
}


def build_task(name: str = "") -> str:
    from api.voice import script
    from api.onboarding import service

    # Reuse all ordering, skip conditions, privacy safeguards and tool instructions.
    # Omit a non-Latin name from the spoken greeting, never from the saved account.
    task = script.build_interview_task("en", name if name.isascii() else "")
    for attr, field in service.fields("en").items():
        if field.ask and attr in QUESTIONS:
            task = task.replace(field.ask, QUESTIONS[attr])
    return (
        "Speak in natural Hinglish: simple spoken Hindi with familiar English words. "
        "The questions below are written in Romanized Hindi. "
        "Opening: 'Namaste ji, main GovAssist ka automated assistant hoon. "
        "Aapne callback maanga tha. Kya abhi baat karna theek rahega?' "
        "Use 'haan ji', 'theek hai' and 'samajh gaya' naturally. "
        "For unclear answers say 'Maaf kijiye ji, ek baar phir bataayenge?' "
        "For uncertainty say 'Koi baat nahi ji, abhi is sawaal ko chhod dete hain.' "
        "Confirm numbers explicitly and never guess. Read server tool results "
        "as supplied, including English names or text; never invent or translate "
        "a result yourself.\n\n" + task
    )

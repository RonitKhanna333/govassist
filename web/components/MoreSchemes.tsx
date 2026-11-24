// Info-only cards for schemes that are NOT in the grounded corpus. They are
// never fed to the rule engine and give no verdict: a short general
// description and the official website, clearly labelled as unchecked.
type Card = { name: string; hi: string; about: string; aboutHi: string; url: string };

const CARDS: Card[] = [
  { name: "PM-KISAN", hi: "पीएम-किसान", url: "https://pmkisan.gov.in",
    about: "Income support of ₹6,000 a year, in three instalments, for landholding farmer families.",
    aboutHi: "ज़मीन वाले किसान परिवारों को साल में ₹6,000 की मदद, तीन किस्तों में।" },
  { name: "Ayushman Bharat PM-JAY", hi: "आयुष्मान भारत पीएम-जय", url: "https://pmjay.gov.in",
    about: "Free hospital treatment cover of up to ₹5 lakh per family per year at listed hospitals.",
    aboutHi: "सूचीबद्ध अस्पतालों में हर परिवार को साल में ₹5 लाख तक का मुफ़्त इलाज।" },
  { name: "PM Awas Yojana – Gramin", hi: "पीएम आवास योजना – ग्रामीण", url: "https://pmayg.nic.in",
    about: "Help for rural families without a pucca house to build one.",
    aboutHi: "गाँव के जिन परिवारों के पास पक्का घर नहीं है, उन्हें घर बनाने में मदद।" },
  { name: "PM Awas Yojana – Urban", hi: "पीएम आवास योजना – शहरी", url: "https://pmay-urban.gov.in",
    about: "Help for urban families to get an affordable pucca house.",
    aboutHi: "शहर के परिवारों को किफ़ायती पक्का घर पाने में मदद।" },
  { name: "Sukanya Samriddhi Yojana", hi: "सुकन्या समृद्धि योजना", url: "https://www.indiapost.gov.in",
    about: "A small-savings account for a girl child, opened at a post office or bank.",
    aboutHi: "बेटी के लिए छोटी बचत का खाता, डाकघर या बैंक में खुलता है।" },
  { name: "PM Mudra Yojana", hi: "पीएम मुद्रा योजना", url: "https://www.mudra.org.in",
    about: "Bank loans without collateral for small non-farm businesses (Shishu, Kishore, Tarun).",
    aboutHi: "छोटे गैर-कृषि कारोबार के लिए बिना गारंटी बैंक लोन (शिशु, किशोर, तरुण)।" },
  { name: "PM-SYM (Shram Yogi Maandhan)", hi: "पीएम श्रम योगी मानधन", url: "https://maandhan.in",
    about: "A contributory pension of ₹3,000 a month after age 60 for unorganised workers.",
    aboutHi: "असंगठित मज़दूरों के लिए 60 साल के बाद ₹3,000 महीना पेंशन, अंशदान वाली।" },
  { name: "e-Shram", hi: "ई-श्रम", url: "https://eshram.gov.in",
    about: "Free registration and an e-Shram card for unorganised workers.",
    aboutHi: "असंगठित मज़दूरों के लिए मुफ़्त पंजीकरण और ई-श्रम कार्ड।" },
  { name: "PM Vishwakarma", hi: "पीएम विश्वकर्मा", url: "https://pmvishwakarma.gov.in",
    about: "Training, a toolkit and credit support for traditional artisans and craftspeople.",
    aboutHi: "पारंपरिक कारीगरों के लिए ट्रेनिंग, औज़ार और लोन की मदद।" },
  { name: "National Scholarship Portal", hi: "राष्ट्रीय छात्रवृत्ति पोर्टल", url: "https://scholarships.gov.in",
    about: "One place to apply for central and state government scholarships.",
    aboutHi: "केंद्र और राज्य सरकार की छात्रवृत्तियों के लिए एक ही जगह आवेदन।" },
];

export function MoreSchemes({ locale }: { locale: string }) {
  const hi = locale === "hi";
  return <section className="more-schemes" aria-labelledby="more-schemes-title">
    <h2 id="more-schemes-title">{hi ? "और योजनाएँ (सिर्फ़ जानकारी)" : "More schemes (info only)"}</h2>
    <p className="note" role="note">{hi
      ? "ये योजनाएँ GovAssist ने सरकारी दस्तावेज़ से नहीं जाँची हैं और इनकी पात्रता नहीं बताई जाती। सही जानकारी के लिए सरकारी वेबसाइट देखें।"
      : "These schemes are not checked against official documents by GovAssist, and no eligibility verdict is given. See the official website for accurate details."}</p>
    <ul>{CARDS.map(card => <li key={card.url}>
      <strong lang={hi ? "hi" : "en"}>{hi ? card.hi : card.name}</strong>
      <span>{hi ? card.aboutHi : card.about}</span>
      <a href={card.url} target="_blank" rel="noopener noreferrer">{hi ? "सरकारी वेबसाइट" : "Official website"} ↗</a>
    </li>)}</ul>
  </section>;
}

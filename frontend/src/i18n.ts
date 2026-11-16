/**
 * Minimal translations. Keys are the English strings themselves, so a missing
 * translation falls back to English instead of showing a blank.
 *
 * The Hindi text was written without a native-speaker review. Please have a
 * Hindi-speaking carpenter or shop owner read through it before relying on it.
 */

export type Language = 'en' | 'hi';

export const LANGUAGES: { code: Language; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
];

const STORAGE_KEY = 'cutlist_language';

function readLanguage(): Language {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'hi' ? 'hi' : 'en';
  } catch {
    return 'en';
  }
}

let current: Language = readLanguage();

export function getLanguage(): Language {
  return current;
}

/** Switch language and reload so every screen picks it up. */
export function setLanguage(language: Language): void {
  current = language;
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  document.documentElement.lang = language;
  window.location.reload();
}

export function t(text: string): string {
  if (current === 'en') return text;
  return HI[text] ?? text;
}

/** Translate a sentence with {named} values in it. */
export function tf(template: string, values: Record<string, string | number>): string {
  const text = t(template).replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ''));
  // English plurals: "1 parts" -> "1 part". Hindi wording here does not change with count.
  return current === 'en' ? text.replace(/\b1 (part|sheet)s\b/g, '1 $1') : text;
}

const HI: Record<string, string> = {
  // ---- Steps and header ----
  'Add your design': 'अपना डिज़ाइन जोड़ें',
  'Check the parts': 'पार्ट्स जाँचें',
  'Cutting plan': 'कटिंग प्लान',
  'Progress': 'प्रगति',
  'Ask': 'पूछें',
  'New job': 'नया काम',
  'Start a new job': 'नया काम शुरू करें',
  'Large designs can take up to a minute.': 'बड़े डिज़ाइन में एक मिनट तक लग सकता है।',
  'Working…': 'काम चल रहा है…',

  // ---- Add your design ----
  'What are you building?': 'आप क्या बना रहे हैं?',
  'Add your furniture design and get a cutting plan: every part, how to cut each sheet, and how many sheets to buy.':
    'अपना फ़र्नीचर डिज़ाइन जोड़ें और कटिंग प्लान पाएँ: हर पार्ट, हर शीट कैसे काटनी है, और कितनी शीट ख़रीदनी हैं।',
  'I have a 3D file': 'मेरे पास 3D फ़ाइल है',
  'From SketchUp, Fusion, Blender…': 'SketchUp, Fusion, Blender… से',
  "I'll describe it": 'मैं बताकर बनाऊँगा',
  'Type the size, we work out the parts': 'साइज़ लिखें, पार्ट्स हम निकालेंगे',
  'Choose your 3D file': 'अपनी 3D फ़ाइल चुनें',
  'Change': 'बदलें',
  'Remove file': 'फ़ाइल हटाएँ',
  'How do I get this file from SketchUp?': 'SketchUp से यह फ़ाइल कैसे निकालें?',
  'Make every board its own': 'हर बोर्ड को अलग बनाएँ:',
  'Hide handles, hinges and screws.': 'हैंडल, कब्ज़े और स्क्रू छिपा दें।',
  'Go to': 'यहाँ जाएँ:',
  'Describe the furniture': 'फ़र्नीचर के बारे में लिखें',
  'Description': 'विवरण',
  'Example: Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves':
    'उदाहरण: Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves',
  'Give height, width and depth in mm, and how many shelves, shutters or drawers.':
    'ऊँचाई, चौड़ाई और गहराई mm में दें, और कितने शेल्फ़, शटर या दराज़ चाहिए। (अभी विवरण अंग्रेज़ी में लिखें।)',
  'We work out every panel with fixed carcass rules and show you the rules used. You check the parts before anything is cut.':
    'हम हर पैनल तय नियमों से निकालते हैं और वे नियम आपको दिखाते हैं। कुछ भी कटने से पहले आप पार्ट्स जाँच लेते हैं।',
  'Your material': 'आपका मटीरियल',
  'Your plywood': 'आपकी प्लाई',
  'Sheet size': 'शीट का साइज़',
  'Other': 'अन्य',
  'Sheet length in mm': 'शीट की लंबाई mm में',
  'Sheet width in mm': 'शीट की चौड़ाई mm में',
  'Main board thickness': 'मुख्य बोर्ड की मोटाई',
  'Thickness in mm': 'मोटाई mm में',
  'Parts in another thickness, like a 6 mm back, are put on their own sheets automatically.':
    'दूसरी मोटाई के पार्ट, जैसे 6 mm का बैक, अपने-आप अलग शीट पर रखे जाते हैं।',
  'Price of one sheet': 'एक शीट की क़ीमत',
  'More settings': 'और सेटिंग',
  'Blade thickness (kerf)': 'ब्लेड की मोटाई (कर्फ़)',
  'Blade thickness': 'ब्लेड की मोटाई',
  'The width of wood the blade removes on each cut. Most panel saws are about 3 mm.':
    'हर कट में ब्लेड जितनी लकड़ी हटाता है। ज़्यादातर पैनल सॉ में यह लगभग 3 mm होती है।',
  'Use my offcut shelf': 'मेरे बचे हुए टुकड़े इस्तेमाल करें',
  'Make cutting plan': 'कटिंग प्लान बनाएँ',

  // ---- Check the parts ----
  'Check the sizes match your design. Rename a part by tapping its name. Switch off anything you do not want cut.':
    'देखें कि साइज़ आपके डिज़ाइन से मिलते हैं। नाम पर टैप करके पार्ट का नाम बदलें। जो नहीं काटना, उसे बंद कर दें।',
  'Every part was measured cleanly.': 'हर पार्ट सही नापा गया।',
  'A quick look at the sizes is still a good idea.': 'फिर भी साइज़ एक बार देख लेना अच्छा है।',
  'They are shown first, with the reason.': 'ये सबसे पहले दिखाए गए हैं, कारण के साथ।',
  'The design did not have them as closed solid boards, so please check their sizes carefully.':
    'डिज़ाइन में ये पूरे ठोस बोर्ड नहीं थे, इसलिए इनके साइज़ ध्यान से जाँचें।',
  'Usually handles, legs or decoration. If one of these is a real board, fix it in the design and upload again.':
    'आम तौर पर ये हैंडल, पाये या सजावट होते हैं। अगर इनमें कोई असली बोर्ड है, तो डिज़ाइन ठीक करके फिर अपलोड करें।',
  'Find a part': 'पार्ट खोजें',
  'Find a part by name or size': 'नाम या साइज़ से पार्ट खोजें',
  'Part shape': 'पार्ट का आकार',
  'Please check': 'कृपया जाँचें',
  'Looks right': 'सही लग रहा है',
  'Include all': 'सब शामिल करें',
  'How these sizes were worked out': 'ये साइज़ कैसे निकाले गए',
  'We could not find any boards': 'हमें कोई बोर्ड नहीं मिला',
  'The file opened, but nothing in it looks like a flat board with thickness.':
    'फ़ाइल खुल गई, पर इसमें मोटाई वाला कोई सपाट बोर्ड नहीं दिखा।',
  'How to fix the design': 'डिज़ाइन कैसे ठीक करें',
  'Draw every board as a solid with its real thickness, not a flat face.':
    'हर बोर्ड को उसकी असली मोटाई के साथ ठोस बनाएँ, सिर्फ़ सपाट सतह नहीं।',
  'Make each board its own group or component.': 'हर बोर्ड को अलग ग्रुप या कंपोनेंट बनाएँ।',
  'Export in millimetres.': 'मिलीमीटर में एक्सपोर्ट करें।',

  // ---- Cutting plan ----
  'Your cutting plan': 'आपका कटिंग प्लान',
  'Change parts': 'पार्ट्स बदलें',
  'Print plan': 'प्लान प्रिंट करें',
  'Summary': 'सारांश',
  'Sheets to buy': 'कितनी शीट ख़रीदनी हैं',
  'Material cost': 'मटीरियल का ख़र्च',
  'Wood used': 'लकड़ी इस्तेमाल हुई',
  'Spare pieces worth keeping': 'रखने लायक बचे टुकड़े',
  'Spare piece worth keeping': 'रखने लायक बचा टुकड़ा',
  'Sheet layout': 'शीट का नक़्शा',
  'Part to cut': 'काटने वाला पार्ट',
  'Waste': 'बेकार',
  'Parts list': 'पार्ट्स की सूची',
  'Qty': 'संख्या',
  'Part': 'पार्ट',
  'Length': 'लंबाई',
  'Width': 'चौड़ाई',
  'Thick': 'मोटाई',
  'Thickness': 'मोटाई',
  'Size': 'साइज़',
  'Area': 'क्षेत्रफल',
  'Downloads': 'डाउनलोड',
  'Take it to the workshop': 'वर्कशॉप ले जाएँ',
  'Print the cutting plan': 'कटिंग प्लान प्रिंट करें',
  'Every sheet and the parts list': 'हर शीट और पार्ट्स की सूची',
  'Part labels': 'पार्ट के लेबल',
  'Stick one on each cut part': 'हर कटे पार्ट पर एक चिपकाएँ',
  'Parts list for Excel': 'Excel के लिए पार्ट्स की सूची',
  'CSV file': 'CSV फ़ाइल',
  'Files for a CNC machine': 'CNC मशीन की फ़ाइलें',
  'DXF, opens in any CAM software': 'DXF, किसी भी CAM सॉफ़्टवेयर में खुलती है',
  'Test with an air cut before using': 'इस्तेमाल से पहले हवा में चलाकर जाँच लें',
  'Labels and machine files are made when you start from a 3D file.':
    'लेबल और मशीन की फ़ाइलें तब बनती हैं जब आप 3D फ़ाइल से शुरू करते हैं।',
  'Made without passing our checks.': 'यह हमारी जाँच पास किए बिना बना है।',
  'You chose to continue, so measure before you cut.': 'आपने आगे बढ़ना चुना, इसलिए काटने से पहले नाप लें।',
  'Good to know': 'जानने लायक',
  'Tips for this job': 'इस काम के लिए सुझाव',
  'This design is not ready to cut': 'यह डिज़ाइन अभी काटने लायक नहीं है',
  'We stopped before making a plan, because the sizes we read may be wrong. Cutting from it could waste sheets.':
    'हमने प्लान बनाने से पहले रोक दिया, क्योंकि पढ़े गए साइज़ ग़लत हो सकते हैं। इससे काटने पर शीट बर्बाद हो सकती हैं।',
  'What we found': 'हमें क्या मिला',
  'How to fix it': 'इसे कैसे ठीक करें',
  'Back to the parts': 'पार्ट्स पर वापस',
  'I have checked the sizes, make the plan anyway': 'मैंने साइज़ जाँच लिए हैं, फिर भी प्लान बनाएँ',

  // ---- Edge banding and quote ----
  'Choose which edges get tape. Taped parts are cut smaller by the tape thickness, so they finish at the right size.':
    'चुनें किन किनारों पर टेप लगेगी। टेप वाले पार्ट टेप की मोटाई जितने छोटे काटे जाते हैं, ताकि अंत में साइज़ सही आए।',
  'Tape thickness': 'टेप की मोटाई',
  'Front edge on all': 'सब पर सामने का किनारा',
  'Clear all': 'सब हटाएँ',
  'Update the cutting plan': 'कटिंग प्लान अपडेट करें',
  'Your customer sees only the total on the shared link, never your costs or margin.':
    'शेयर किए लिंक पर ग्राहक को सिर्फ़ कुल रक़म दिखती है, आपका ख़र्च या मुनाफ़ा कभी नहीं।',
  'Labour': 'मज़दूरी',
  'Hardware': 'हार्डवेयर',
  'Your margin': 'आपका मुनाफ़ा',
  'Customer name': 'ग्राहक का नाम',
  'Note on the quote': 'कोटेशन पर नोट',
  'Example: Price valid for 15 days': 'उदाहरण: क़ीमत 15 दिन तक मान्य',
  'Quote total': 'कोटेशन की कुल रक़म',
  'Save quote': 'कोटेशन सेव करें',
  'Remove': 'हटाएँ',
  'Saved. Share the project link to send it.': 'सेव हो गया। भेजने के लिए प्रोजेक्ट का लिंक शेयर करें।',

  // ---- Cut lengths ----
  'Cut lengths': 'लंबाई काटें',
  'For timber, beading, pipe and profiles. List the lengths you need and we fit them onto the fewest bars.':
    'लकड़ी, बीडिंग, पाइप और प्रोफ़ाइल के लिए। जो लंबाइयाँ चाहिए वे लिखें, हम उन्हें सबसे कम छड़ों में बैठा देंगे।',
  'What to cut': 'क्या काटना है',
  'Pieces you need': 'आपको चाहिए ये टुकड़े',
  'Length mm': 'लंबाई mm',
  'Add another piece': 'एक और टुकड़ा जोड़ें',
  'Length of one bar': 'एक छड़ की लंबाई',
  'Bar length in mm': 'छड़ की लंबाई mm में',
  'Price of one bar': 'एक छड़ की क़ीमत',
  'Leftover lengths you already have': 'आपके पास पहले से बचे टुकड़े',
  'In mm, separated by commas. These are used first and cost nothing.':
    'mm में, कॉमा से अलग करके। ये पहले इस्तेमाल होते हैं और इनका कोई ख़र्च नहीं।',
  'Work out the cuts': 'कट निकालें',
  'Your cutting plan will appear here.': 'आपका कटिंग प्लान यहाँ दिखेगा।',
  'Bars to buy': 'कितनी छड़ें ख़रीदनी हैं',
  'Cost': 'ख़र्च',
  'How to cut each bar': 'हर छड़ कैसे काटें',
  'Print': 'प्रिंट',
  'Leftovers worth keeping:': 'रखने लायक बचे टुकड़े:',

  // ---- Projects ----
  'Your projects': 'आपके प्रोजेक्ट',
  'New project': 'नया प्रोजेक्ट',
  'Sign out': 'साइन आउट',
  'Sign in': 'साइन इन',
  'No projects yet': 'अभी कोई प्रोजेक्ट नहीं',
  'Upload a 3D model to get your first cutting plan.': 'पहला कटिंग प्लान पाने के लिए 3D मॉडल अपलोड करें।',
  'Open plan': 'प्लान खोलें',
  'Share': 'शेयर करें',
  'Copy share link': 'शेयर लिंक कॉपी करें',
  'Copy': 'कॉपी',
  'Save offcuts': 'बचे टुकड़े सेव करें',
  'Save reusable offcuts': 'दोबारा काम आने वाले टुकड़े सेव करें',
  'Offcut shelf': 'बचे टुकड़ों की शेल्फ़',
  'Discard': 'हटा दें',
  'Discard offcut': 'टुकड़ा हटा दें',
  'Run again': 'फिर से चलाएँ',
  'Ready': 'तैयार',
  'Failed': 'नहीं हो पाया',
  'Processing…': 'काम चल रहा है…',
  'Queued': 'क़तार में',
  'Making the cutting plan…': 'कटिंग प्लान बन रहा है…',
  'Dismiss': 'बंद करें',
  'Resend email': 'ईमेल फिर भेजें',
  'Close': 'बंद करें',
  'Name': 'नाम',
  'Created': 'बनाया गया',
  'Last used': 'आख़िरी बार इस्तेमाल',

  // ---- Help chat ----
  'Ask about this job': 'इस काम के बारे में पूछें',
  'Answers are written by AI. Check before relying on them.': 'जवाब AI लिखता है। भरोसा करने से पहले जाँच लें।',
  'Ask anything about this cutting plan, the material or how to build it.':
    'इस कटिंग प्लान, मटीरियल या बनाने के तरीक़े के बारे में कुछ भी पूछें।',
  'Type your question': 'अपना सवाल लिखें',
  'Your question': 'आपका सवाल',
  'Send': 'भेजें',

  // ---- AI: assistant, voice, sketch photo ----
  'Ask AI': 'AI से पूछें',
  'Ask about this plan, or ask for a change. You approve every change before it is made.':
    'इस प्लान के बारे में पूछें, या कोई बदलाव माँगें। हर बदलाव आपकी मंज़ूरी के बाद ही होता है।',
  'Check this plan for problems': 'इस प्लान में कमी जाँचें',
  'Put tape on the front edge of every part': 'हर पार्ट के सामने के किनारे पर टेप लगाएँ',
  'Write a WhatsApp message for my customer': 'ग्राहक के लिए WhatsApp संदेश लिखें',
  'How many sheets for 3 of these?': 'ऐसे 3 के लिए कितनी शीट लगेंगी?',
  'The cutting plan will be made again with this change.': 'इस बदलाव के साथ कटिंग प्लान दोबारा बनेगा।',
  'Saves the quote. Your customer sees only the total.': 'कोटेशन सेव होगा। ग्राहक को सिर्फ़ कुल रक़म दिखती है।',
  'Apply this change': 'यह बदलाव लागू करें',
  'Applied': 'लागू हो गया',
  'Say it': 'बोलकर बताएँ',
  'Stop and write it down': 'रोकें और लिख लें',
  'Photo of a sketch': 'स्केच की फ़ोटो',
  'Speak or type in any language, or photograph a drawing with the sizes written on it.':
    'किसी भी भाषा में बोलें या लिखें, या नाप लिखी ड्रॉइंग की फ़ोटो लें।',
  'Writing down what you said…': 'आपकी बात लिखी जा रही है…',
  'Reading the sizes from your photo…': 'फ़ोटो से नाप पढ़े जा रहे हैं…',
  'This is what we heard. Check the sizes and correct anything wrong.':
    'हमने यह सुना। नाप जाँच लें और जो ग़लत हो उसे ठीक करें।',
  'This is what we read from the photo. Check every size against your drawing.':
    'फ़ोटो से हमने यह पढ़ा। हर नाप अपनी ड्रॉइंग से मिला लें।',
  'We could not read every size. Add the missing ones:': 'हम हर नाप नहीं पढ़ पाए। बचे हुए नाप जोड़ें:',
  'We could not use the microphone. Allow it in your browser, then try again.':
    'माइक्रोफ़ोन इस्तेमाल नहीं हो सका। ब्राउज़र में इजाज़त दें, फिर कोशिश करें।',
  'We could not hear that recording. Try again.': 'रिकॉर्डिंग सुनाई नहीं दी। फिर कोशिश करें।',
  'We could not read that photo. Try again in better light.': 'फ़ोटो पढ़ी नहीं जा सकी। अच्छी रोशनी में फिर कोशिश करें।',
  'height': 'ऊँचाई',
  'width': 'चौड़ाई',
  'depth': 'गहराई',

  // ---- Sheet view ----
  'Zoom': 'ज़ूम',
  'Zoom in': 'बड़ा करें',
  'Zoom out': 'छोटा करें',
  'Problems with the 3D model': '3D मॉडल की समस्याएँ',
  'This 3D model has problems that affect the plan': 'इस 3D मॉडल में ऐसी समस्याएँ हैं जो प्लान पर असर डालती हैं',
  'What to do': 'क्या करें',
  'Explained by AI. Every number comes from the checks of your model.': 'AI ने समझाया है। हर संख्या आपके मॉडल की जाँच से आई है।',
  'What the software found': 'सॉफ़्टवेयर को क्या मिला',
  'Upload a 3D model, get nested sheet layouts, DXF, G-code and a workshop-ready parts list — in one click.': '3D मॉडल अपलोड करें और एक क्लिक में शीट का नक़्शा, DXF, G-code और वर्कशॉप के लिए पार्ट्स की लिस्ट पाएँ।',
  'Welcome back': 'वापसी पर स्वागत है',
  'Forgot your password?': 'पासवर्ड भूल गए?',
  'Choose a new password': 'नया पासवर्ड चुनें',
  'Forgot password?': 'पासवर्ड भूल गए?',
  'Back to sign in': 'साइन इन पर वापस जाएँ',
  'Send me the link': 'मुझे लिंक भेजें',
  'Save password and sign in': 'पासवर्ड सेव करें और साइन इन करें',
  'New password': 'नया पासवर्ड',
  'At least 8 characters': 'कम से कम 8 अक्षर',
  'Enter your email and we will send you a link to choose a new password.': 'अपना ईमेल लिखें, हम नया पासवर्ड चुनने का लिंक भेजेंगे।',
  'If that email has an account, we have sent a link to choose a new password. It works once, for one hour.': 'अगर इस ईमेल का अकाउंट है, तो हमने नया पासवर्ड चुनने का लिंक भेज दिया है। यह एक घंटे तक, सिर्फ़ एक बार काम करता है।',
  'By creating an account you agree to the': 'अकाउंट बनाकर आप इन्हें मानते हैं:',
  'and': 'और',
  'Terms': 'शर्तें',
  'Privacy Policy': 'प्राइवेसी पॉलिसी',
  'Try it without an account →': 'बिना अकाउंट के आज़माएँ →',
  'Delete project': 'प्रोजेक्ट हटाएँ',
  'Delete "{name}"? Its files and share link are removed for good. This cannot be undone.': '"{name}" हटाएँ? इसकी फ़ाइलें और शेयर लिंक हमेशा के लिए मिट जाएँगे। इसे वापस नहीं किया जा सकता।',
  'Account': 'अकाउंट',
  'Deleting your account removes every project, file, share link, API key and saved offcut. It cannot be undone.': 'अकाउंट हटाने पर हर प्रोजेक्ट, फ़ाइल, शेयर लिंक, API कुंजी और सेव किए बचे टुकड़े मिट जाते हैं। इसे वापस नहीं किया जा सकता।',
  'Delete your account and all your data for good?': 'अपना अकाउंट और सारा डेटा हमेशा के लिए हटाएँ?',
  'Your password': 'आपका पासवर्ड',
  'Delete my account': 'मेरा अकाउंट हटाएँ',
  'Something went wrong on this screen': 'इस स्क्रीन पर कुछ गड़बड़ हो गई',
  'Your projects are safe. Reload the page to carry on.': 'आपके प्रोजेक्ट सुरक्षित हैं। आगे बढ़ने के लिए पेज दोबारा लोड करें।',
  'Reload the page': 'पेज दोबारा लोड करें',
  'Tape and grain': 'टेप और ग्रेन',
  'Grain: a part with its grain locked keeps its length along the sheet and is never turned 90°.': 'ग्रेन: ग्रेन लॉक वाले पार्ट की लंबाई शीट की लंबाई की दिशा में ही रहती है और उसे 90° नहीं घुमाया जाता।',
  'Grain on all': 'सभी में ग्रेन लॉक',
  'Grain off on all': 'सभी में ग्रेन खुला',
  'Lock the grain': 'ग्रेन लॉक करें',
  'Could not save the part settings. Try again.': 'पार्ट की सेटिंग सेव नहीं हो सकी। फिर कोशिश करें।',
  'Cutting order': 'कटाई का क्रम',
  '{n} cuts': '{n} कट',
  'Stage {n}': 'चरण {n}',
  'top edge': 'ऊपर के किनारे',
  'left edge': 'बाएँ किनारे',
  'Cut the {piece} piece: {d} mm from the {edge}': '{piece} का टुकड़ा काटें: {edge} से {d} मिमी पर',
  'Trim the waste off the {piece} piece: {d} mm from the {edge}': '{piece} के टुकड़े से बेकार हिस्सा काटें: {edge} से {d} मिमी पर',
  'part {list} done': 'पार्ट {list} तैयार',
  'Show the cut lines on the sheet': 'शीट पर कट की लाइनें दिखाएँ',
  'This sheet needs no cuts: one part fills it.': 'इस शीट पर कट की ज़रूरत नहीं: एक ही पार्ट पूरी शीट है।',
  'This sheet cannot be cut with straight edge-to-edge cuts, so no cutting order is given.': 'इस शीट को सीधे आर-पार कट से नहीं काटा जा सकता, इसलिए कटाई का क्रम नहीं दिया गया।',
  'Distances are to the near side of the blade. The {kerf} mm blade cuts into the gap beyond it.': 'दूरी ब्लेड के पास वाले किनारे तक नापी गई है। {kerf} मिमी का ब्लेड उसके आगे की ख़ाली जगह में कटता है।',
  'Fit to screen': 'स्क्रीन में पूरा दिखाएँ',
  'Spare': 'बचा हुआ',
  'Tape': 'टेप',
  'Turned 90° on the sheet': 'शीट पर 90° घुमाया गया',
  'Kinds of part on this sheet': 'इस शीट पर पार्ट के प्रकार',
  'Show these on the sheet': 'शीट पर इन्हें दिखाएँ',

  // ---- Account and landing ----
  'Email': 'ईमेल',
  'Password': 'पासवर्ड',
  'Create account': 'खाता बनाएँ',
  'Create a free account': 'मुफ़्त खाता बनाएँ',
  'Create your free account': 'अपना मुफ़्त खाता बनाएँ',
  'Already have an account?': 'पहले से खाता है?',
  'New here?': 'नए हैं?',
  'From 3D model to cutting plan, in one click': '3D मॉडल से कटिंग प्लान, एक क्लिक में',
  'Start free — no card needed': 'मुफ़्त शुरू करें — कार्ड की ज़रूरत नहीं',
  'Free plan: 50 projects a month': 'मुफ़्त प्लान: महीने में 50 प्रोजेक्ट',
  'Simple pricing': 'सीधी क़ीमत',
  'Free': 'मुफ़्त',
  'Coming soon': 'जल्द आ रहा है',
  'Unlimited projects': 'असीमित प्रोजेक्ट',
  'All export formats': 'सभी एक्सपोर्ट फ़ॉर्मैट',
  'Turning designs into cut lists': 'डिज़ाइन को कट लिस्ट में बदलना',
  // ---- Options and progress messages ----
  'No tape': 'टेप नहीं',
  'Front edge': 'सामने का किनारा',
  'Both long edges': 'दोनों लंबे किनारे',
  'All 4 edges': 'चारों किनारे',
  'Reading your design and finding the parts…': 'आपका डिज़ाइन पढ़कर पार्ट्स निकाले जा रहे हैं…',
  'Working out the parts from your description…': 'आपके विवरण से पार्ट्स निकाले जा रहे हैं…',
  'Fitting the parts onto sheets…': 'पार्ट्स शीट पर बैठाए जा रहे हैं…',
  'Uploading your design…': 'आपका डिज़ाइन अपलोड हो रहा है…',
  'Updating the cutting plan…': 'कटिंग प्लान अपडेट हो रहा है…',
  'Saving the quote…': 'कोटेशन सेव हो रहा है…',
  'Queuing a fresh run…': 'नया रन क़तार में लग रहा है…',
  'Sending the verification email…': 'वेरिफ़िकेशन ईमेल भेजा जा रहा है…',
  'Creating API key…': 'API की बन रही है…',
  // ---- Sentences with numbers ----
  '{parts} parts on {sheets} sheets. Tap a part in the list to find it on the sheet.':
    '{sheets} शीट पर {parts} पार्ट। शीट पर ढूँढने के लिए सूची में पार्ट पर टैप करें।',
  'at the sheet price you entered': 'आपकी बताई शीट की क़ीमत पर',
  '{percent}% is left over': '{percent}% बच जाता है',
  'shown hatched in green': 'हरी धारियों में दिखाए गए',
  '{parts} parts · {percent}% used': '{parts} पार्ट · {percent}% इस्तेमाल',
  'Edge banding': 'एज बैंडिंग (किनारे की टेप)',
  '{metres} m of tape': '{metres} m टेप',
  '{metres} m of tape needed': '{metres} m टेप चाहिए',
  'Buy about 10% extra for trimming.': 'कटाई-छँटाई के लिए लगभग 10% ज़्यादा ख़रीदें।',
  'Quote for your customer': 'ग्राहक के लिए कोटेशन',
  'We found {count} parts': 'हमें {count} पार्ट मिले',
  '{count} of {total} parts will be cut': '{total} में से {count} पार्ट काटे जाएँगे',
};

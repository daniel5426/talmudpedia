import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Mapping of English book names to Hebrew
const BOOK_MAPPINGS: Record<string, string> = {
  // Torah
  "Genesis": "בראשית",
  "Exodus": "שמות",
  "Leviticus": "ויקרא",
  "Numbers": "במדבר",
  "Deuteronomy": "דברים",
  
  // Prophets
  "Joshua": "יהושע",
  "Judges": "שופטים",
  "Samuel I": "שמואל א",
  "Samuel II": "שמואל ב",
  "Kings I": "מלכים א",
  "Kings II": "מלכים ב",
  "Isaiah": "ישעיהו",
  "Jeremiah": "ירמיהו",
  "Ezekiel": "יחזקאל",
  "Hosea": "הושע",
  "Joel": "יואל",
  "Amos": "עמוס",
  "Obadiah": "עובדיה",
  "Jonah": "יונה",
  "Micah": "מיכה",
  "Nahum": "נחום",
  "Habakkuk": "חבקוק",
  "Zephaniah": "צפניה",
  "Haggai": "חגי",
  "Zechariah": "זכריה",
  "Malachi": "מלאכי",

  // Writings
  "Psalms": "תהילים",
  "Proverbs": "משלי",
  "Job": "איוב",
  "Song of Songs": "שיר השירים",
  "Ruth": "רות",
  "Lamentations": "איכה",
  "Ecclesiastes": "קהלת",
  "Esther": "אסתר",
  "Daniel": "דניאל",
  "Ezra": "עזרא",
  "Nehemiah": "נחמיה",
  "Chronicles I": "דברי הימים א",
  "Chronicles II": "דברי הימים ב",

  // Talmud Bavli
  "Berakhot": "ברכות",
  "Shabbat": "שבת",
  "Eruvin": "עירובין",
  "Pesachim": "פסחים",
  "Shekalim": "שקלים",
  "Yoma": "יומא",
  "Sukkah": "סוכה",
  "Beitzah": "ביצה",
  "Rosh Hashanah": "ראש השנה",
  "Taanit": "תענית",
  "Megillah": "מגילה",
  "Moed Katan": "מועד קטן",
  "Chagigah": "חגיגה",
  "Yevamot": "יבמות",
  "Ketubot": "כתובות",
  "Nedarim": "נדרים",
  "Nazir": "נזיר",
  "Sotah": "סוטה",
  "Gittin": "גיטין",
  "Kiddushin": "קידושין",
  "Bava Kamma": "בבא קמא",
  "Bava Metzia": "בבא מציעא",
  "Bava Batra": "בבא בתרא",
  "Sanhedrin": "סנהדרין",
  "Makkot": "מכות",
  "Shevuot": "שבועות",
  "Avodah Zarah": "עבודה זרה",
  "Horayot": "הוריות",
  "Zevachim": "זבחים",
  "Menachot": "מנחות",
  "Chullin": "חולין",
  "Bekhorot": "בכורות",
  "Arakhin": "ערכין",
  "Temurah": "תמורה",
  "Keritot": "כריתות",
  "Meilah": "מעילה",
  "Tamid": "תמיד",
  "Middot": "מידות",
  "Kinnim": "קינים",
  "Niddah": "נידה",
  
  // Mishnah (some overlap)
  "Peah": "פאה",
  "Demai": "דמאי",
  "Kilayim": "כלאיים",
  "Sheviit": "שביעית",
  "Terumot": "תרומות",
  "Maasrot": "מעשרות",
  "Maaser Sheni": "מעשר שני",
  "Challah": "חלה",
  "Orlah": "ערלה",
  "Bikkurim": "ביכורים",
};

// Helper to convert numbers to Hebrew numerals (Gematria)
function toHebrewNumeral(num: number): string {
  if (num <= 0) return String(num);
  
  const ones = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט'];
  const tens = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ'];
  const hundreds = ['', 'ק', 'ר', 'ש', 'ת'];
  
  let result = '';
  
  // Handle hundreds
  let h = Math.floor(num / 100);
  while (h > 0) {
    if (h >= 4) {
      result += hundreds[4];
      h -= 4;
    } else {
      result += hundreds[h];
      h = 0;
    }
  }
  
  // Handle tens and ones
  let t = Math.floor((num % 100) / 10);
  let o = num % 10;
  
  // Special cases for 15 (טו) and 16 (טז)
  if (t === 1 && o === 5) {
    result += 'טו';
  } else if (t === 1 && o === 6) {
    result += 'טז';
  } else {
    result += tens[t] + ones[o];
  }
  
  // Add geresh or gershayim
  if (result.length === 1) {
    result += "'";
  } else if (result.length > 1) {
    result = result.slice(0, -1) + '"' + result.slice(-1);
  }
  
  return result;
}

export function convertToHebrew(text: string): string {
  if (!text) return text;

  // 1. Try to match exact book names
  let hebrewText = text;
  
  // Sort keys by length descending to match longest first
  const sortedKeys = Object.keys(BOOK_MAPPINGS).sort((a, b) => b.length - a.length);
  
  for (const book of sortedKeys) {
    if (hebrewText.includes(book)) {
      hebrewText = hebrewText.replace(book, BOOK_MAPPINGS[book]);
    }
  }

  // 2. Handle "Page Xa/b" or "Daf Xa/b" format (e.g., "Berakhot 2a")
  // Regex for Book Name + Number + a/b
  // This is tricky because we already replaced the book name.
  // Let's look for patterns like "Book Hebrew Name" + " " + "2a"
  
  // Replace "Page" or "Daf"
  hebrewText = hebrewText.replace(/\bPage\b/g, 'דף').replace(/\bDaf\b/g, 'דף');
  
  // Handle standard Talmud citation: "2a", "2b", "102a"
  // We look for a number followed by 'a' or 'b' at the end of string or followed by space
  hebrewText = hebrewText.replace(/\b(\d+)([ab])\b/g, (match, numStr, side) => {
    const num = parseInt(numStr);
    const hebrewNum = toHebrewNumeral(num);
    const sideHebrew = side === 'a' ? 'ע״א' : 'ע״ב';
    return `${hebrewNum} ${sideHebrew}`;
  });

  // Handle Chapter/Verse citations: "Chapter 1", "1:1"
  // "Genesis 1:1" -> "בראשית א א" or similar
  // This is complex to do perfectly without context, but let's do basic number conversion
  
  // Convert "Chapter X"
  hebrewText = hebrewText.replace(/\bChapter\s+(\d+)\b/g, (match, num) => {
    return `פרק ${toHebrewNumeral(parseInt(num))}`;
  });

  // Convert "Verse X"
  hebrewText = hebrewText.replace(/\bVerse\s+(\d+)\b/g, (match, num) => {
    return `פסוק ${toHebrewNumeral(parseInt(num))}`;
  });

  return hebrewText;
}

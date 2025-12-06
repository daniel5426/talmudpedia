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
  "Be'er HaGolah": "באר הגולה",
  "on": "על",
  
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
  
  // Shulchan Arukh
  "Shulchan Arukh": "שולחן ערוך",
  "Orach Chayim": "אורח חיים",
  "Orach Chaim": "אורח חיים",
  "Yoreh Deah": "יורה דעה",
  "Yoreh De'ah": "יורה דעה",
  "Even HaEzer": "אבן העזר",
  "Even Ha'ezer": "אבן העזר",
  "Choshen Mishpat": "חושן משפט",
};

const SORTED_BOOK_KEYS = Object.keys(BOOK_MAPPINGS).sort((a, b) => b.length - a.length);
const SHULCHAN_ARUKH_BOOK_KEYS = [
  "Orach Chayim",
  "Orach Chaim",
  "Yoreh Deah",
  "Yoreh De'ah",
  "Even HaEzer",
  "Even Ha'ezer",
  "Choshen Mishpat",
];
const RANGE_DELIMITER = /(\s*[–—־-]\s*)/;
const RANGE_ONLY = /^\s*[–—־-]\s*$/;

class HebrewReferenceConverter {
  private readonly trimShulchanArukh: boolean;

  constructor(private readonly rawText: string) {
    const lowerText = rawText?.toLowerCase() ?? "";
    const hasShulchanArukh = lowerText.includes("shulchan arukh");
    const hasSpecificBook = SHULCHAN_ARUKH_BOOK_KEYS.some((book) => lowerText.includes(book.toLowerCase()));
    this.trimShulchanArukh = hasShulchanArukh && hasSpecificBook;
  }

  convert(): string {
    if (!this.rawText) return this.rawText;
    const parts = this.rawText.split(RANGE_DELIMITER);
    const convertedParts = parts.map((part) => (RANGE_ONLY.test(part) ? part : this.convertSegment(part)));
    return this.mergeRangeSegments(convertedParts).join("");
  }

  private convertSegment(segment: string): string {
    if (!segment) return segment;
    let formatted = segment;
    formatted = this.replaceBookNames(formatted);
    formatted = this.replacePageMarkers(formatted);
    formatted = this.replaceDafNotation(formatted);
    formatted = this.replaceChapterVerseWords(formatted);
    formatted = this.replaceColonReferences(formatted);
    formatted = this.replaceStandaloneNumbers(formatted);
    if (this.trimShulchanArukh) {
      formatted = this.removeRedundantShulchanArukh(formatted);
    }
    return formatted;
  }

  private mergeRangeSegments(parts: string[]): string[] {
    const merged: string[] = [];
    let index = 0;
    while (index < parts.length) {
      const token = parts[index];
      if (RANGE_ONLY.test(token) && merged.length > 0 && index + 1 < parts.length) {
        const previousIndex = merged.length - 1;
        const previous = merged[previousIndex];
        const next = parts[index + 1];
        const collapsed = this.collapseRangeSegment(previous, token, next);
        if (collapsed) {
          merged[previousIndex] = collapsed;
          index += 2;
          continue;
        }
      }
      merged.push(token);
      index += 1;
    }
    return merged;
  }

  private collapseRangeSegment(start: string, delimiter: string, end: string): string | null {
    if (!start || !end) {
      return null;
    }
    const sharedLength = this.sharedPrefixLength(start, end);
    if (sharedLength === 0) {
      return null;
    }
    const suffix = end.slice(sharedLength).trimStart();
    if (!suffix) {
      return null;
    }
    return `${start}${delimiter}${suffix}`;
  }

  private sharedPrefixLength(a: string, b: string): number {
    const max = Math.min(a.length, b.length);
    let index = 0;
    while (index < max && a[index] === b[index]) {
      index += 1;
    }
    return index;
  }

  private replaceBookNames(value: string): string {
    let result = value;
    for (const book of SORTED_BOOK_KEYS) {
      if (result.includes(book)) {
        result = result.split(book).join(BOOK_MAPPINGS[book]);
      }
    }
    return result;
  }

  private replacePageMarkers(value: string): string {
    return value.replace(/\bPage\b/g, "דף").replace(/\bDaf\b/g, "דף");
  }

  private replaceDafNotation(value: string): string {
    return value.replace(/\b(\d+)([ab])\b/g, (match, numStr, side) => {
      const num = parseInt(numStr, 10);
      const hebrewNum = HebrewReferenceConverter.toHebrewNumeral(num);
      const sideHebrew = side === "a" ? "ע״א" : "ע״ב";
      return `${hebrewNum} ${sideHebrew}`;
    });
  }

  private replaceChapterVerseWords(value: string): string {
    return value
      .replace(/\bChapter\s+(\d+)\b/g, (match, num) => {
        return `פרק ${HebrewReferenceConverter.toHebrewNumeral(parseInt(num, 10))}`;
      })
      .replace(/\bVerse\s+(\d+)\b/g, (match, num) => {
        return `פסוק ${HebrewReferenceConverter.toHebrewNumeral(parseInt(num, 10))}`;
      });
  }

  private replaceColonReferences(value: string): string {
    return value.replace(/\b(\d+):(\d+)\b/g, (match, num1, num2) => {
      return `${HebrewReferenceConverter.toHebrewNumeral(parseInt(num1, 10))}:${HebrewReferenceConverter.toHebrewNumeral(parseInt(num2, 10))}`;
    });
  }

  private replaceStandaloneNumbers(value: string): string {
    return value.replace(/(^|[,\s])(\d+)(?=\s|$)/g, (match, prefix, numStr) => {
      const num = parseInt(numStr, 10);
      if (num < 1 || num > 999 || Number.isNaN(num)) {
        return match;
      }
      const hebrewNum = HebrewReferenceConverter.toHebrewNumeral(num);
      return `${prefix ?? ""}${hebrewNum}`;
    });
  }

  private removeRedundantShulchanArukh(value: string): string {
    return value.replace(/שולחן ערוך(?:[,]\s*)?/g, "");
  }

  private static toHebrewNumeral(num: number): string {
    if (num <= 0) return String(num);
    const ones = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"];
    const tens = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"];
    const hundreds = ["", "ק", "ר", "ש", "ת"];
    let result = "";
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
    const t = Math.floor((num % 100) / 10);
    const o = num % 10;
    if (t === 1 && o === 5) {
      result += "טו";
    } else if (t === 1 && o === 6) {
      result += "טז";
    } else {
      result += tens[t] + ones[o];
    }
    if (result.length === 1) {
      result += '\u05F3'; // Geresh (׳)
    } else if (result.length > 1) {
      result = result.slice(0, -1) + '\u05F4' + result.slice(-1); // Gershayim (״) before last character
    }
    return result;
  }
}

export function convertToHebrew(text: string): string {
  return new HebrewReferenceConverter(text).convert();
}

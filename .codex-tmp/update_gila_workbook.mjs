import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/danielbenassaya/Downloads/אקסל מחקר גילה.xlsx";
const outputPath = "/Users/danielbenassaya/Downloads/אקסל מחקר גילה - הושלם 2026-04-22.xlsx";
const previewPath = "/Users/danielbenassaya/Downloads/אקסל מחקר גילה - הושלם 2026-04-22.png";

const rows = [
  ["תוצאת חיפוש ציבורית של Yad2", 2150000, 4.5, "1", 90, "דירה", "ליש", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=4.5&neighborhood=856", "snippet-only", "מחיר, רחוב, חדרים, קומה ומ\"ר הופיעו ב-snippet ציבורי; הדף עצמו לא היה נגיש ישירות מהסביבה הזאת."],
  ["תוצאת חיפוש ציבורית של Yad2", 2250000, 3, "3", 99, "דירה", "ורדינון 5", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&neighborhood=856", "snippet-only", "ה-snippet הציבורי הראה ירידת מחיר של 40,000 ש\"ח ונוף פתוח לפארק."],
  ["תוצאת חיפוש ציבורית של Yad2", 2270000, 4, "4", 80, "דירה", "אפרסמון", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=4&neighborhood=856&property=1", "snippet-only", "ה-snippet מציג דירת 4 חדרים בגילה, ירושלים."],
  ["תוצאת חיפוש ציבורית של Yad2", 2390000, 4, "2", 85, "דירה", "השליו", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&neighborhood=856", "snippet-only", "ה-snippet הציג 2 מרפסות."],
  ["תוצאת חיפוש ציבורית של Yad2", 2390000, 4, "2", 86, "דירה", "מבוא הקינמון", "https://www.yad2.co.il/realestate/agency/4091290/forsale?sort=price-asc", "snippet-only", "ה-snippet הגיע מעמוד סוכנות בגילה."],
  ["תוצאת חיפוש ציבורית של Yad2", 2490000, 5, "1", 110, "דירה", "הצוף", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=5&neighborhood=856&property=1", "snippet-only", "לא הופיעו פרטי מעלית/מחסן/חניה ב-snippet."],
  ["תוצאת חיפוש ציבורית של Yad2", 2650000, 4, "קרקע", 84, "דירת גן", "הדולב", "https://www.yad2.co.il/realestate/forsale?area=7&city=3000&maxRooms=4&minRooms=4&neighborhood=856&propertyGroup=misc&topArea=100", "snippet-only", "ה-snippet מציג דירת גן בגילה."],
  ["תוצאת חיפוש ציבורית של Yad2", 2700000, 4.5, "1", 90, "דירה", "הצוף 1", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=4&neighborhood=856&property=1", "snippet-only", "ה-snippet הציבורי הציג דירת 4.5 חדרים."],
  ["תוצאת חיפוש ציבורית של Yad2", 2820000, 6, "2", 116, "דירה", "מבוא קציעה", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=4.5&neighborhood=856", "snippet-only", "ה-snippet הציג ממ\"ד."],
  ["תוצאת חיפוש ציבורית של Yad2", 2890000, 5, "קרקע", 89, "דירה", "אגמון 3", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&minRooms=5&neighborhood=856&property=1", "snippet-only", "ה-snippet הגיע מעמוד דירות 5 חדרים בגילה."],
  ["תוצאת חיפוש ציבורית של Yad2", 3450000, 4, "2", 130, "דירה", "אבנר חי שאקי", "https://www.yad2.co.il/realestate/forsale/partnership/jerusalem?area=7&city=3000&neighborhood=856", "snippet-only", "ה-snippet הציבורי הציג 130 מ\"ר ודירה בגילה."],
];

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.add("השלמות ציבוריות 2026-04-22");

const headers = [[
  "מקור",
  "מחיר",
  "מספר חדרים",
  "קומה",
  "מ\"ר",
  "סוג נכס",
  "רחוב / כותרת",
  "קישור מקור",
  "סטטוס אימות",
  "הערה",
]];

sheet.getRange("A1:J1").values = headers;
sheet.getRange(`A2:J${rows.length + 1}`).values = rows;
sheet.getRange(`B2:B${rows.length + 1}`).numberFormat = '#,##0';
sheet.getRange(`C2:C${rows.length + 1}`).numberFormat = '0.0';
sheet.getRange(`E2:E${rows.length + 1}`).numberFormat = '0.0';

try {
  sheet.getRange("A1:J1").format.fill.color = "#FDE9D9";
  sheet.getRange("A1:J1").format.horizontalAlignment = "center";
  sheet.getRange("A:J").format.wrapText = true;
  await sheet.freezePanes.freezeRows(1);
} catch (error) {
  console.log("Formatting warning:", error.message);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const blob = await workbook.render({ sheetName: "השלמות ציבוריות 2026-04-22", range: `A1:J${rows.length + 1}`, scale: 1.5 });
await fs.writeFile(previewPath, Buffer.from(await blob.arrayBuffer()));

console.log(JSON.stringify({ outputPath, previewPath, rows: rows.length }));

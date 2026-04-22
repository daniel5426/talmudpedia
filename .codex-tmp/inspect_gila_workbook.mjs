import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/danielbenassaya/Downloads/אקסל מחקר גילה.xlsx";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

console.log("Workbook keys:", Object.keys(workbook));
console.log("Worksheets type:", typeof workbook.worksheets);
console.log("Worksheets keys:", Object.keys(workbook.worksheets || {}));
for (let i = 0; i < 10; i += 1) {
  try {
    const sheet = workbook.worksheets.getItemAt(i);
    if (!sheet) {
      break;
    }
    console.log(`\nSHEET ${i}:`, sheet.name);
    console.log("Used range:", sheet.usedRange?.address);
    const values = await sheet.getRange("A1:Z20").values;
    console.log(JSON.stringify(values));
  } catch (error) {
    console.log(`Stopped at index ${i}:`, error.message);
    break;
  }
}

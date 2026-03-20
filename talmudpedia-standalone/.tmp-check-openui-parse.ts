import fs from 'node:fs';
import { createParser } from '@openuidev/react-lang';
import { openuiChatLibrary } from './node_modules/.pnpm/@openuidev+react-ui@0.9.18_@openuidev+react-headless@0.7.9_react-dom@19.2.4_react@19.2._8ec1d50be9761599c42e72f4c3987958/node_modules/@openuidev/react-ui/dist/genui-lib/openuiChatLibrary.js';
const runs = JSON.parse(fs.readFileSync('/tmp/latest_openui_runs.json', 'utf8')) as Array<{run_id:string; assistant_output_text:string}>;
for (const run of runs) {
  const parser = createParser(openuiChatLibrary);
  const result = parser.parse(run.assistant_output_text || '');
  console.log('RUN', run.run_id);
  console.log('ROOT', Boolean(result.root));
  console.log('INCOMPLETE', Boolean(result.meta?.incomplete));
  console.log('UNRESOLVED', JSON.stringify(result.meta?.unresolved || []));
  console.log('ERRORS', JSON.stringify(result.meta?.validationErrors || []));
  console.log('STATEMENTS', result.meta?.statementCount ?? null);
  console.log('---');
}

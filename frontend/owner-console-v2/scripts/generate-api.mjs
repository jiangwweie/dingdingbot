import {spawnSync} from 'node:child_process';
import {writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
const frontend=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const root=resolve(frontend,'../..');
function run(command,args){const result=spawnSync(command,args,{cwd:root,encoding:'utf8'});if(result.status!==0)throw new Error(result.stderr||result.stdout);return result.stdout;}
const json=run(resolve(root,'.venv/bin/python'),['scripts/owner_console/export_openapi.py']);
await mkdir(resolve(frontend,'.local'),{recursive:true});
const schema=resolve(frontend,'.local/owner-console.json');await writeFile(schema,json);
const output=run(resolve(frontend,'node_modules/.bin/openapi-typescript'),[schema]);
await writeFile(resolve(frontend,'src/api/schema.d.ts'),output);

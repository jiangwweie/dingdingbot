const fs = require('fs');
const { execSync } = require('child_process');

const files = execSync('find src -type f -name "*.tsx" -o -name "*.css"').toString().split('\n').filter(Boolean);

const regexes = [
  { match: /(?<!dark:)bg-zinc-950/g, replace: 'bg-white dark:bg-zinc-950' },
  { match: /(?<!dark:)bg-zinc-900(\/[0-9]+)?/g, replace: 'bg-zinc-50 dark:bg-zinc-900$1' },
  { match: /(?<!(dark:|hover:))bg-zinc-800(\/[0-9]+)?/g, replace: 'bg-zinc-100 dark:bg-zinc-800$1' },
  { match: /(?<!(dark:|hover:))bg-zinc-700(\/[0-9]+)?/g, replace: 'bg-zinc-200 dark:bg-zinc-700$1' },
  
  { match: /(?<!dark:)border-zinc-800(\/[0-9]+)?/g, replace: 'border-zinc-200 dark:border-zinc-800$1' },
  { match: /(?<!dark:)border-zinc-700(\/[0-9]+)?/g, replace: 'border-zinc-300 dark:border-zinc-700$1' },

  { match: /(?<!dark:)text-zinc-100/g, replace: 'text-zinc-900 dark:text-zinc-100' },
  { match: /(?<!dark:)text-zinc-200/g, replace: 'text-zinc-800 dark:text-zinc-200' },
  { match: /(?<!dark:)text-zinc-300/g, replace: 'text-zinc-700 dark:text-zinc-300' },
  { match: /(?<!dark:)text-zinc-400/g, replace: 'text-zinc-600 dark:text-zinc-400' },
  
  { match: /(?<!dark:)hover:bg-zinc-800(\/[0-9]+)?/g, replace: 'hover:bg-zinc-100 dark:hover:bg-zinc-800$1' },
  { match: /(?<!dark:)hover:bg-zinc-700(\/[0-9]+)?/g, replace: 'hover:bg-zinc-200 dark:hover:bg-zinc-700$1' },
  
  { match: /(?<!dark:)(?<!\w-)text-white/g, replace: 'text-zinc-900 dark:text-white' },
];

for (const file of files) {
  let content = fs.readFileSync(file, 'utf8');
  let original = content;
  
  for (const { match, replace } of regexes) {
    content = content.replace(match, replace);
  }
  
  // Custom manual replacements
  content = content.replace('hover:text-white', 'hover:text-zinc-900 dark:hover:text-white');
  
  if (content !== original) {
    fs.writeFileSync(file, content);
    console.log('Updated', file);
  }
}

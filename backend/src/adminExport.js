// Run locally as a server maintainer. Opens the existing database READ ONLY.
const sqlite3=require('sqlite3');
const {getDbPath}=require('./database/init_db');
async function main() {
  const [kind,...flags]=process.argv.slice(2);
  if (!['feedback','reports'].includes(kind) || flags.some(x=>x!=='--index-only') || (kind==='feedback' && flags.length)) {
    throw new Error('Usage: node src/adminExport.js feedback | reports [--index-only]');
  }
  const file=getDbPath();
  const database=await new Promise((resolve,reject)=>{
    const connection=new sqlite3.Database(file,sqlite3.OPEN_READONLY,error=>error?reject(error):resolve(connection));
  });
  try {
    const read={all:sql=>new Promise((resolve,reject)=>database.all(sql,(error,rows)=>error?reject(error):resolve(rows)))};
    const options={database:read,dbPath:file,indexOnly:flags.includes('--index-only')};
    const result=kind==='feedback'
      ? await require('./normative/feedbackArchive').refreshFeedbackArchive(options)
      : await require('./normative/adminDataExport').exportAllReports(options);
    console.log(JSON.stringify(result,null,2));
  } finally {await new Promise((resolve,reject)=>database.close(error=>error?reject(error):resolve()));}
}
main().catch(error=>{console.error('Maintenance export failed:',error.message);process.exitCode=1;});

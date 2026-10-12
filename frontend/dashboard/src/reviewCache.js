// Memory only. Refreshing dashboard data invalidates the review snapshot.
const entries=new Map()
export const clearReviewCache=()=>entries.clear()
export const cachedReview=key=>entries.get(key)?.data
export function readReview(key,loader){
  if(entries.has(key))return entries.get(key).promise
  if(entries.size>=150)entries.delete(entries.keys().next().value)
  const entry={}
  entry.promise=Promise.resolve().then(loader).then(data=>{entry.data=data;return data}).catch(error=>{if(entries.get(key)===entry)entries.delete(key);throw error})
  entries.set(key,entry)
  return entry.promise
}

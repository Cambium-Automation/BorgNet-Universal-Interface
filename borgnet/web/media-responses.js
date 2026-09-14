// Public provider output is always rendered as text, never interpreted as HTML.
window.borgnetProviderResponses = record => {
  const details = document.createElement('details');
  details.className = 'provider-responses';
  const summary = document.createElement('summary');
  summary.textContent = 'Provider responses';
  details.append(summary);
  const add = text => {const p=document.createElement('p');p.textContent=text;details.append(p);};
  const replies = record.provider_responses || [];
  let found = false;
  for (const reply of replies) {
    for (const message of reply.messages || []) {add(message);found=true;}
    if (reply.codes?.length) {add('Provider codes: '+reply.codes.join(' · '));found=true;}
    if (reply.truncated) add('Response exceeded the storage limit; some content was truncated.');
  }
  if (!found) add('No public provider text was recorded for this attempt.');
  if (record.error) add('BorgNet status: '+record.error);
  add('Public replies and refusal details are saved with history. Credentials and URLs are removed; private reasoning and raw payloads are excluded. Clearing history removes these records.');
  return details;
};

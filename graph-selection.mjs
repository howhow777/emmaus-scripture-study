// DOM-free rules shared by canvas taps and the keyboard-accessible result list.
export function selectionAfterTap(currentId, tappedId) {
  return tappedId && tappedId !== currentId ? tappedId : null;
}

export function hashAfterSelection(currentHash, previousId, nextId) {
  if (nextId?.startsWith('entry:')) return `#${nextId.slice('entry:'.length)}`;
  if (nextId) return /^#E\d+$/.test(currentHash) ? '' : currentHash;
  const previousHash = previousId?.startsWith('entry:') ? `#${previousId.slice('entry:'.length)}` : null;
  return currentHash === previousHash ? '' : currentHash;
}

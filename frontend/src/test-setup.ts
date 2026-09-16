/** Browser globals the request layer touches, for tests that run in Node.
 *
 * Assigned directly rather than through `vi.stubGlobal`, because a test calling
 * `vi.unstubAllGlobals()` to release its fetch stub would otherwise take
 * localStorage away with it.
 */
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  clear() {
    this.store.clear();
  }
}

(globalThis as unknown as { localStorage: Storage }).localStorage =
  new MemoryStorage() as unknown as Storage;

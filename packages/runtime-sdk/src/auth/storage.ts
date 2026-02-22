export type RuntimeTokenStore = {
  get: () => string | null;
  set: (token: string) => void;
  clear: () => void;
};

const TOKEN_PREFIX = "published-app-auth-token";

export function createLocalStorageTokenStore(appSlug: string, prefix: string = TOKEN_PREFIX): RuntimeTokenStore {
  const key = `${prefix}:${appSlug}`;
  return {
    get: () => {
      if (typeof window === "undefined") return null;
      return window.localStorage.getItem(key);
    },
    set: (token: string) => {
      if (typeof window === "undefined") return;
      window.localStorage.setItem(key, token);
    },
    clear: () => {
      if (typeof window === "undefined") return;
      window.localStorage.removeItem(key);
    },
  };
}

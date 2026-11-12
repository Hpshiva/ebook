import axios, { AxiosError } from "axios";

const TOKEN_KEY = "creator_finder_token";

export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export const http = axios.create({ baseURL: import.meta.env.VITE_API_URL ?? "" });

http.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

http.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/")) onUnauthorized();
    return Promise.reject(error);
  },
);

/** Turn any API failure into one readable sentence. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
    if (!error.response) return "Cannot reach the server. Is the backend running?";
    return `Request failed (${error.response.status})`;
  }
  return error instanceof Error ? error.message : "Something went wrong";
}

type Params = Record<string, string | number | boolean | null | undefined>;
const clean = (params?: Params) =>
  Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v !== "" && v !== null && v !== undefined));

export const api = {
  get: async <T>(url: string, params?: Params) => (await http.get<T>(url, { params: clean(params) })).data,
  post: async <T>(url: string, body?: unknown) => (await http.post<T>(url, body ?? {})).data,
  put: async <T>(url: string, body?: unknown) => (await http.put<T>(url, body ?? {})).data,
  patch: async <T>(url: string, body?: unknown) => (await http.patch<T>(url, body ?? {})).data,
  del: async <T>(url: string) => (await http.delete<T>(url)).data,
};

/** Download an export through the authenticated API and save it. */
export async function downloadExport(params: Params) {
  const res = await http.get("/api/export", { params: clean(params), responseType: "blob" });
  const name = /filename="([^"]+)"/.exec(res.headers["content-disposition"] ?? "")?.[1] ?? `export.${params.fmt}`;
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

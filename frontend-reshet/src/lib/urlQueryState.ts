export function coerceQueryEnum<T extends string>(
  value: string | null,
  allowedValues: readonly T[],
  fallback: T,
): T {
  if (value && allowedValues.includes(value as T)) {
    return value as T
  }
  return fallback
}

export function buildQueryStringWithValue(
  currentSearchParams: string,
  key: string,
  value: string,
  fallbackValue?: string,
): string {
  const params = new URLSearchParams(currentSearchParams)
  if (fallbackValue !== undefined && value === fallbackValue) {
    params.delete(key)
  } else {
    params.set(key, value)
  }
  return params.toString()
}

"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import { buildQueryStringWithValue, coerceQueryEnum } from "@/lib/urlQueryState"

type UseUrlEnumStateOptions<T extends string> = {
  key: string
  allowedValues: readonly T[]
  fallback: T
}

export function useUrlEnumState<T extends string>({
  key,
  allowedValues,
  fallback,
}: UseUrlEnumStateOptions<T>) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()

  const urlValue = useMemo(
    () => coerceQueryEnum(searchParams.get(key), allowedValues, fallback),
    [allowedValues, fallback, key, searchParams],
  )
  const [value, setValue] = useState<T>(urlValue)

  useEffect(() => {
    setValue(urlValue)
  }, [urlValue])

  const updateValue = useCallback((nextValue: T) => {
    setValue(nextValue)
    const nextQuery = buildQueryStringWithValue(searchParams.toString(), key, nextValue, fallback)
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false })
  }, [fallback, key, pathname, router, searchParams])

  return [value, updateValue] as const
}

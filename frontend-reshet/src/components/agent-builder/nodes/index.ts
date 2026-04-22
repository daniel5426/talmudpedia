import { BaseNode } from "./BaseNode"

export const nodeTypes = new Proxy({} as Record<string, typeof BaseNode>, {
  get: (target, prop: string) => {
    if (prop in target) {
      return target[prop]
    }
    if (typeof prop === "string" && prop.length > 0) {
      return BaseNode
    }
    return undefined
  }
})

"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

type FileSpaceMarkdownPreviewProps = {
  content: string
}

export function FileSpaceMarkdownPreview({ content }: FileSpaceMarkdownPreviewProps) {
  return (
    <div className="h-full overflow-auto px-5 py-4">
      <div className="mx-auto w-full max-w-4xl">
        <article className="space-y-4 text-sm leading-7 text-foreground [&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted/70 [&_code]:px-1.5 [&_code]:py-0.5 [&_h1]:text-3xl [&_h1]:font-semibold [&_h2]:text-2xl [&_h2]:font-semibold [&_h3]:text-xl [&_h3]:font-semibold [&_hr]:border-border [&_img]:rounded-xl [&_img]:border [&_img]:border-border/60 [&_li]:ml-5 [&_ol]:list-decimal [&_p]:text-foreground/95 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-border/60 [&_pre]:bg-muted/40 [&_pre]:p-4 [&_table]:w-full [&_table]:border-collapse [&_tbody_tr]:border-b [&_td]:border [&_td]:border-border/60 [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-border/60 [&_th]:bg-muted/40 [&_th]:px-3 [&_th]:py-2 [&_thead]:text-left [&_ul]:list-disc">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </article>
      </div>
    </div>
  )
}

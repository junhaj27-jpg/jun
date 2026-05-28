const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  AlignmentType,
  BorderStyle,
  WidthType,
  ShadingType,
  VerticalAlign,
  HeadingLevel,
  ImageRun,
  TableLayoutType,
  PageOrientation,
  PageBreak,
} = require("docx");
const fs = require("fs");
const path = require("path");

const payload = JSON.parse(fs.readFileSync("__ARCH_INPUT_JSON__", "utf-8"));
const outputPath = "__ARCH_OUTPUT_DOCX__";
const ROOT_DIR = path.resolve(__dirname, "..");

const PAGE_W = 16838;
const PAGE_H = 11906;
const MARGIN = 720;
const TABLE_W = PAGE_W - MARGIN * 2;
const COLOR = {
  title: "1F2937",
  text: "111827",
  muted: "4B5563",
  header: "D9EAF7",
  label: "F3F4F6",
  white: "FFFFFF",
  border: "9CA3AF",
};

const border = { style: BorderStyle.SINGLE, size: 1, color: COLOR.border };
const borders = { top: border, bottom: border, left: border, right: border };

function asText(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value ?? "");
}

function listText(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join("\n");
  return asText(value);
}

function run(value, opts = {}) {
  return new TextRun({
    text: asText(value),
    bold: opts.bold || false,
    size: opts.size || 18,
    font: "Malgun Gothic",
    color: opts.color || COLOR.text,
  });
}

function paragraph(value, opts = {}) {
  return new Paragraph({
    heading: opts.heading,
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    spacing: { before: opts.before ?? 80, after: opts.after ?? 80 },
    bullet: opts.bullet ? { level: 0 } : undefined,
    children: [run(value, opts)],
  });
}

function cellParagraphs(value, opts = {}) {
  const lines = asText(value).split(/\r?\n/);
  return (lines.length ? lines : [""]).map((line) =>
    new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { before: 0, after: 40 },
      children: [run(line, { bold: opts.bold, size: opts.size || 16, color: opts.color })],
    })
  );
}

function cell(value, opts = {}) {
  return new TableCell({
    borders,
    width: opts.width ? { size: opts.width, type: WidthType.DXA } : undefined,
    shading: {
      fill: opts.fill || (opts.header ? COLOR.header : opts.label ? COLOR.label : COLOR.white),
      type: ShadingType.CLEAR,
    },
    verticalAlign: VerticalAlign.TOP,
    columnSpan: opts.span || 1,
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    children: cellParagraphs(value, opts),
  });
}

function table(rows, widths) {
  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    layout: TableLayoutType.FIXED,
    rows: rows.map(
      (row, rowIndex) =>
        new TableRow({
          tableHeader: rowIndex === 0,
          children: row.map((item, colIndex) => {
            const opts = typeof item === "object" && item !== null && "value" in item ? item : { value: item };
            return cell(opts.value, {
              width: widths[colIndex],
              header: rowIndex === 0 || opts.header,
              label: opts.label,
              bold: rowIndex === 0 || opts.bold,
              center: rowIndex === 0 || opts.center,
              size: opts.size || (rowIndex === 0 ? 17 : 16),
              fill: opts.fill,
            });
          }),
        })
    ),
  });
}

function requirements() {
  return payload.requirement_doc?.requirements || [];
}

function analyzedById() {
  const map = new Map();
  for (const item of payload.analyzed_reqs || []) {
    if (item.requirement_id) map.set(item.requirement_id, item);
  }
  return map;
}

function buildRevisionTable() {
  return table(
    [
      ["날짜", "버전", "작성자", "승인자", "변경 내용"],
      ["", "v1.0", "", "", "아키텍처 설계서 초안 작성"],
    ],
    [2200, 1500, 2200, 2200, TABLE_W - 8100]
  );
}

function buildSummaryTable() {
  const infra = payload.user_infra_spec || {};
  const extracted = payload.extracted_infra || {};
  const rows = [
    ["미들웨어 스택", infra.middleware_stack || listText(extracted.selected_middleware)],
    ["방화벽 구성", infra.firewall_setting],
    ["보안/인증", infra.security_auth || extracted.security_architecture],
    ["예상 동시 사용자", infra.expected_ccu],
    ["구축 환경", infra.is_cloud === true ? "Cloud" : "On-Premise"],
    ["서버 사양", infra.server_hardware_spec],
  ];

  return table([["구분", "내용"], ...rows], [3000, TABLE_W - 3000]);
}

function buildRequirementMappingTable() {
  const analyzed = analyzedById();
  const rows = [
    ["요구사항 ID", "요구사항명", "구분/우선순위", "주요 설계 반영"],
  ];

  for (const req of requirements()) {
    const analysis = analyzed.get(req.requirement_id) || {};
    rows.push([
      req.requirement_id || "",
      req.requirement_name || "",
      `${req.requirement_type || ""}\n${req.priority ? `우선순위: ${req.priority}` : ""}`,
      `비기능 요소: ${asText(analysis.non_functional_elements)}\n필요 구성: ${asText(analysis.implied_middleware_needs)}`,
    ]);
  }

  if (rows.length === 1) {
    rows.push(["", "요구사항 데이터가 없습니다.", "", ""]);
  }

  return table(rows, [1800, 4300, 2500, TABLE_W - 8600]);
}

function buildRequirementDetailSections() {
  const analyzed = analyzedById();
  const extracted = payload.extracted_infra || {};
  const children = [];

  for (const req of requirements()) {
    const analysis = analyzed.get(req.requirement_id) || {};
    children.push(
      paragraph(`${req.requirement_id || ""} ${req.requirement_name || ""}`, {
        heading: HeadingLevel.HEADING_3,
        bold: true,
        size: 20,
        before: 180,
      })
    );
    children.push(
      table(
        [
          ["항목", "내용"],
          ["요구사항 설명", req.description || ""],
          ["제약조건", listText(req.constraints)],
          ["검증 기준", listText(req.validation_criteria)],
          ["비기능 요소", listText(analysis.non_functional_elements)],
          ["기술 제약", listText(analysis.technical_constraints)],
          ["필요 미들웨어/구성", listText(analysis.implied_middleware_needs)],
          [
            "구현 방안",
            [
              `적용 아키텍처: ${listText(extracted.system_architecture)}`,
              `선정 미들웨어: ${listText(extracted.selected_middleware)}`,
              `보안 반영: ${extracted.security_architecture || ""}`,
            ].join("\n\n"),
          ],
        ],
        [2600, TABLE_W - 2600]
      )
    );
  }

  if (!children.length) {
    children.push(paragraph("요구사항 상세 데이터가 없습니다.", { color: COLOR.muted }));
  }

  return children;
}

function buildComponentTable() {
  const extracted = payload.extracted_infra || {};
  const components = extracted.system_architecture || [];
  const middleware = new Set(extracted.selected_middleware || []);
  const rows = [["구성요소", "구분", "설계 반영 내용"]];

  for (const component of components) {
    rows.push([
      component,
      middleware.has(component) ? "선정 미들웨어/플랫폼" : "아키텍처 구성요소",
      `${component}를 온프레미스 내부망 아키텍처 구성에 반영하고, 요구사항 매핑 표의 관련 기능 구현에 사용합니다.`,
    ]);
  }

  if (rows.length === 1) {
    rows.push(["", "", "도출된 인프라 구성요소가 없습니다."]);
  }

  return table(rows, [3600, 3300, TABLE_W - 6900]);
}

function cleanMarkdownish(value) {
  return asText(value)
    .replace(/```markdown/gi, "")
    .replace(/```/g, "")
    .split(/\r?\n/)
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) return true;
      if (trimmed.startsWith("|")) return false;
      if (/^-{3,}$/.test(trimmed.replace(/\|/g, "").trim())) return false;
      return true;
    })
    .join("\n")
    .trim();
}

function markdownishToParagraphs(content) {
  const cleaned = cleanMarkdownish(content);
  if (!cleaned) return [paragraph("추가 설명 데이터가 없습니다.", { color: COLOR.muted })];

  const children = [];
  for (const raw of cleaned.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      children.push(new Paragraph({ text: "" }));
    } else if (line.startsWith("### ")) {
      children.push(paragraph(line.slice(4), { heading: HeadingLevel.HEADING_3, bold: true, size: 22 }));
    } else if (line.startsWith("## ")) {
      children.push(paragraph(line.slice(3), { heading: HeadingLevel.HEADING_2, bold: true, size: 24 }));
    } else if (line.startsWith("# ")) {
      children.push(paragraph(line.slice(2), { heading: HeadingLevel.HEADING_1, bold: true, size: 26 }));
    } else if (line.startsWith("- ")) {
      children.push(paragraph(line.replace(/^\-\s*/, "").replace(/\*\*/g, ""), { bullet: true }));
    } else {
      children.push(paragraph(line.replace(/\*\*/g, "")));
    }
  }
  return children;
}

function pngSize(buffer) {
  if (
    buffer.length >= 24 &&
    buffer.readUInt32BE(0) === 0x89504e47 &&
    buffer.readUInt32BE(12) === 0x49484452
  ) {
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }
  return { width: 1200, height: 675 };
}

function resolveImagePath(imagePath) {
  if (!imagePath) return null;
  if (path.isAbsolute(imagePath)) return imagePath;
  return path.resolve(ROOT_DIR, imagePath);
}

function buildImageParagraph(imagePath) {
  const resolved = resolveImagePath(imagePath);
  if (!resolved || !fs.existsSync(resolved)) {
    return paragraph("아키텍처 이미지가 생성되지 않았습니다.", { color: COLOR.muted });
  }

  const data = fs.readFileSync(resolved);
  const size = pngSize(data);
  const maxWidth = 920;
  const width = Math.min(maxWidth, size.width);
  const height = Math.round((size.height / size.width) * width);

  return new Paragraph({
    spacing: { before: 160, after: 160 },
    alignment: AlignmentType.CENTER,
    children: [
      new ImageRun({
        type: "png",
        data,
        transformation: { width, height },
      }),
    ],
  });
}

function codeParagraph(value) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    children: [
      new TextRun({
        text: asText(value),
        font: "Consolas",
        size: 14,
        color: COLOR.muted,
      }),
    ],
  });
}

const children = [
  paragraph("아키텍처 설계서", {
    heading: HeadingLevel.TITLE,
    bold: true,
    size: 34,
    color: COLOR.title,
    before: 0,
    after: 240,
  }),
  paragraph("1. 제개정 이력", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 160 }),
  buildRevisionTable(),
  paragraph("2. 인프라 구성 요약", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  buildSummaryTable(),
  paragraph("3. 요구사항별 아키텍처 매핑", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  buildRequirementMappingTable(),
  paragraph("4. 요구사항 상세 설계", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  ...buildRequirementDetailSections(),
  paragraph("5. 시스템 구성요소 설계", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  buildComponentTable(),
  paragraph("6. 보안 아키텍처", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  table([["항목", "내용"], ["보안 설계", payload.extracted_infra?.security_architecture || ""]], [2600, TABLE_W - 2600]),
  new Paragraph({ children: [new PageBreak()] }),
  paragraph("7. 시스템 아키텍처 다이어그램", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 0 }),
  buildImageParagraph(payload.image_path),
  paragraph("8. 생성 상세 설명", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 240 }),
  ...markdownishToParagraphs(payload.report_specs || ""),
];

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: "Malgun Gothic", size: 18 },
        paragraph: { spacing: { after: 80 } },
      },
    },
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H, orientation: PageOrientation.LANDSCAPE },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      children,
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(outputPath, buffer);
  console.log("완료");
});

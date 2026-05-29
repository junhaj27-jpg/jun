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
  PageBreak,
} = require("docx");
const fs = require("fs");
const path = require("path");

const payload = JSON.parse(fs.readFileSync("__ARCH_INPUT_JSON__", "utf-8"));
const outputPath = "__ARCH_OUTPUT_DOCX__";
const ROOT_DIR = path.resolve(__dirname, "..");

const PAGE_W = 11906;
const PAGE_H = 16838;
const MARGIN = 850;
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

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map((item) => String(item));
  const text = asText(value).trim();
  return text ? [text] : [];
}

function truncate(value, max = 180) {
  const text = asText(value).replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
}

function run(value, opts = {}) {
  return new TextRun({
    text: asText(value),
    bold: opts.bold || false,
    size: opts.size || 19,
    font: "Malgun Gothic",
    color: opts.color || COLOR.text,
  });
}

function paragraph(value, opts = {}) {
  return new Paragraph({
    heading: opts.heading,
    alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    spacing: { before: opts.before ?? 60, after: opts.after ?? 90 },
    bullet: opts.bullet ? { level: 0 } : undefined,
    children: [run(value, opts)],
  });
}

function body(value) {
  return paragraph(value, { size: 19, before: 20, after: 90 });
}

function bullet(value) {
  return paragraph(value, { bullet: true, size: 18, before: 10, after: 45 });
}

function cellParagraphs(value, opts = {}) {
  const lines = asText(value).split(/\r?\n/);
  return (lines.length ? lines : [""]).map((line) =>
    new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { before: 0, after: 25 },
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
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
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
          children: row.map((value, colIndex) =>
            cell(value, {
              width: widths[colIndex],
              header: rowIndex === 0,
              bold: rowIndex === 0,
              center: rowIndex === 0,
              size: rowIndex === 0 ? 16 : 15,
            })
          ),
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

function buildMetaTable() {
  const infra = payload.user_infra_spec || {};
  const rows = [
    ["구분", "내용"],
    ["구축 형태", infra.is_cloud === true ? "Cloud" : "On-Premise"],
    ["미들웨어", infra.middleware_stack || ""],
    ["예상 동시 사용자", infra.expected_ccu ?? ""],
    ["서버 사양", infra.server_hardware_spec || ""],
    ["방화벽/인증", [infra.firewall_setting, infra.security_auth].filter(Boolean).join(" / ")],
  ];
  return table(rows, [2300, TABLE_W - 2300]);
}

function buildComponentTable() {
  const extracted = payload.extracted_infra || {};
  const rows = [["구성 영역", "주요 구성요소", "역할"]];
  const components = asList(extracted.system_architecture);
  const middleware = asList(extracted.selected_middleware);

  rows.push([
    "AI 실행",
    components.filter((x) => /AI|Kubernetes|GPU|모델|LLM/i.test(x)).join(", ") || components.slice(0, 3).join(", "),
    "온프레미스 내부망에서 LLM 실행, 모델 운영, GPU 추론 처리를 담당합니다.",
  ]);
  rows.push([
    "검색/RAG",
    components.filter((x) => /RAG|검색|벡터|Vector|Hybrid/i.test(x)).join(", ") || middleware.filter((x) => /RAG|검색|벡터|Vector|Hybrid/i.test(x)).join(", "),
    "문서 임베딩, 의미 검색, 하이브리드 검색 및 응답 근거 검색을 담당합니다.",
  ]);
  rows.push([
    "문서 처리",
    components.filter((x) => /문서|파일|DRM|Q&A/i.test(x)).join(", ") || middleware.filter((x) => /문서|파일|DRM/i.test(x)).join(", "),
    "업로드 문서 처리, 저장, DRM 복호화 및 질의응답 연계를 담당합니다.",
  ]);
  rows.push([
    "인증/연계",
    components.filter((x) => /SSO|ERP|인증|세션/i.test(x)).join(", ") || middleware.filter((x) => /SSO|ERP|인증|세션/i.test(x)).join(", "),
    "SSO, ERP, 세션 검증, 조직 정보 동기화 등 외부 연계와 접근 제어를 담당합니다.",
  ]);

  return table(rows, [1900, 4200, TABLE_W - 6100]);
}

function buildTraceabilityTable() {
  const analyzed = analyzedById();
  const rows = [["요구사항 ID", "요구사항명", "설계 반영"]];
  for (const req of requirements()) {
    const analysis = analyzed.get(req.requirement_id) || {};
    rows.push([
      req.requirement_id || "",
      req.requirement_name || "",
      truncate(asText(analysis.implied_middleware_needs || analysis.technical_constraints), 160),
    ]);
  }
  if (rows.length === 1) rows.push(["", "요구사항 데이터가 없습니다.", ""]);
  return table(rows, [1500, 3000, TABLE_W - 4500]);
}

function resolveImagePath(imagePath) {
  if (!imagePath) return null;
  if (path.isAbsolute(imagePath)) return imagePath;
  return path.resolve(ROOT_DIR, imagePath);
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

function buildImageParagraph(imagePath) {
  const resolved = resolveImagePath(imagePath);
  if (!resolved || !fs.existsSync(resolved)) {
    return paragraph("아키텍처 이미지가 생성되지 않았습니다.", { color: COLOR.muted });
  }

  const data = fs.readFileSync(resolved);
  const size = pngSize(data);
  const maxWidth = 620;
  const width = Math.min(maxWidth, size.width);
  const height = Math.round((size.height / size.width) * width);

  return new Paragraph({
    spacing: { before: 120, after: 160 },
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

const extracted = payload.extracted_infra || {};

const children = [
  paragraph("아키텍처 설계서", {
    heading: HeadingLevel.TITLE,
    bold: true,
    size: 34,
    color: COLOR.title,
    before: 0,
    after: 220,
  }),

  paragraph("1. 설계 개요", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 100 }),
  body("본 문서는 온프레미스 생성형 AI 플랫폼 구축을 위한 논리 아키텍처와 주요 인프라 구성요소를 정의합니다. 요구사항 원문을 반복하기보다, 실제 설계에 반영되는 실행 환경, 검색/RAG, 문서 처리, 인증/연계, 보안 경계를 중심으로 정리합니다."),
  bullet(`구성요소: ${asText(extracted.system_architecture)}`),
  bullet(`선정 미들웨어: ${asText(extracted.selected_middleware)}`),
  bullet(`보안 방향: ${extracted.security_architecture || "보안 아키텍처 데이터 없음"}`),

  paragraph("2. 인프라 조건", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 180 }),
  buildMetaTable(),

  paragraph("3. 시스템 구성", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 180 }),
  buildComponentTable(),

  paragraph("4. 시스템 아키텍처 다이어그램", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 180 }),
  buildImageParagraph(payload.image_path),

  new Paragraph({ children: [new PageBreak()] }),
  paragraph("5. 보안 및 연계 설계", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 0 }),
  body(extracted.security_architecture || "보안 아키텍처 데이터가 없습니다."),
  bullet("DMZ와 내부망 사이의 방화벽 정책을 기준으로 외부 접근 경로를 제한합니다."),
  bullet("SSO/ERP 연계는 세션 검증 모듈과 권한 관리 체계를 통해 통제합니다."),
  bullet("문서 처리 및 RAG 검색 구간은 내부망 저장소와 벡터DB를 기준으로 폐쇄망 운영을 전제합니다."),

  paragraph("6. 요구사항 추적성", { heading: HeadingLevel.HEADING_2, bold: true, size: 24, before: 180 }),
  buildTraceabilityTable(),
];

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: "Malgun Gothic", size: 19 },
        paragraph: { spacing: { after: 80 } },
      },
    },
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H },
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

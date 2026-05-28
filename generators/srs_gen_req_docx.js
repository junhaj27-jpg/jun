const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign,
  HeadingLevel
} = require('docx');
const fs = require('fs');

const reqs = JSON.parse(fs.readFileSync('/home/claude/sample_reqs.json', 'utf-8'));

const GRAY  = "D9D9D9";
const WHITE = "FFFFFF";
const STATUS_COLORS = {
  "신규": "E8F5E9",
  "수정": "E3F2FD",
  "기존": "FFFFFF",
};
const PAGE_W = 15840;
const MARGIN  = 720;
const TABLE_W = PAGE_W - MARGIN * 2;

const border  = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, opts = {}) {
  const fill = opts.fill || (opts.shade ? GRAY : WHITE);
  return new TableCell({
    borders,
    width: opts.width ? { size: opts.width, type: WidthType.DXA } : undefined,
    shading: { fill, type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,
    columnSpan: opts.span || 1,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({
      alignment: opts.center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({
        text: String(text ?? ""),
        bold: opts.bold || false,
        size: opts.size || 18,
        font: "Malgun Gothic",
      })]
    })]
  });
}

function buildRevisionTable() {
  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    columnWidths: [1500, 1200, 1500, 1500, TABLE_W - 5700],
    rows: [
      new TableRow({ children: [
        cell("날짜",   { shade: true, bold: true, center: true, width: 1500 }),
        cell("버전",   { shade: true, bold: true, center: true, width: 1200 }),
        cell("작성자", { shade: true, bold: true, center: true, width: 1500 }),
        cell("승인자", { shade: true, bold: true, center: true, width: 1500 }),
        cell("내용",   { shade: true, bold: true, center: true, width: TABLE_W - 5700 }),
      ]}),
      ...Array(3).fill(null).map(() =>
        new TableRow({ children: [
          cell("", { width: 1500 }),
          cell("", { width: 1200 }),
          cell("", { width: 1500 }),
          cell("", { width: 1500 }),
          cell("", { width: TABLE_W - 5700 }),
        ]})
      ),
    ]
  });
}

const COLS = [1200, 1800, 900, TABLE_W - 10500, 1800, 1500, 900, 1500, 1500, 900];

function buildHeaderRow() {
  return new TableRow({
    tableHeader: true,
    children: [
      cell("요구사항\nID",   { shade: true, bold: true, center: true, width: COLS[0] }),
      cell("요구사항명",     { shade: true, bold: true, center: true, width: COLS[1] }),
      cell("구분",           { shade: true, bold: true, center: true, width: COLS[2] }),
      cell("요구사항 설명",  { shade: true, bold: true, center: true, width: COLS[3] }),
      cell("요구사항 출처",  { shade: true, bold: true, center: true, width: COLS[4] }),
      cell("제약사항",       { shade: true, bold: true, center: true, width: COLS[5] }),
      cell("중요도",         { shade: true, bold: true, center: true, width: COLS[6] }),
      cell("해결방안",       { shade: true, bold: true, center: true, width: COLS[7] }),
      cell("검수기준",       { shade: true, bold: true, center: true, width: COLS[8] }),
      cell("상태",           { shade: true, bold: true, center: true, width: COLS[9] }),
    ]
  });
}

function buildReqRow(req) {
  const source      = Array.isArray(req.source)              ? req.source.join(", ")              : (req.source || "");
  const constraints = Array.isArray(req.constraints)         ? req.constraints.join("\n")         : (req.constraints || "");
  const criteria    = Array.isArray(req.validation_criteria) ? req.validation_criteria.join("\n") : (req.validation_criteria || "");
  const status      = req.status || "기존";
  const fill        = STATUS_COLORS[status] || WHITE;

  return new TableRow({
    children: [
      cell(req.requirement_id   || "", { width: COLS[0], center: true, fill }),
      cell(req.requirement_name || "", { width: COLS[1], fill }),
      cell(req.requirement_type || "", { width: COLS[2], center: true, fill }),
      cell(req.description      || "", { width: COLS[3], fill }),
      cell(source,                     { width: COLS[4], fill }),
      cell(constraints,                { width: COLS[5], fill }),
      cell(req.priority         || "", { width: COLS[6], center: true, fill }),
      cell(req.note             || "", { width: COLS[7], fill }),
      cell(criteria,                   { width: COLS[8], fill }),
      cell(status,                     { width: COLS[9], center: true, fill }),
    ]
  });
}

function buildMainTable(requirements) {
  const metaRow1 = new TableRow({ children: [
    cell("R1",                    { shade: true, bold: true, center: true, width: COLS[0], size: 22 }),
    cell("사용자 요구사항 정의서", { bold: true, center: true, span: 9, width: TABLE_W - COLS[0], size: 22 }),
  ]});
  const metaRow2 = new TableRow({ children: [
    cell("시스템명",     { shade: true, bold: true, center: true }),
    cell("",             { span: 3 }),
    cell("서브시스템명", { shade: true, bold: true, center: true }),
    cell("",             { span: 3 }),
    cell("배전",         { shade: true, bold: true, center: true }),
    cell(""),
  ]});
  const metaRow3 = new TableRow({ children: [
    cell("단계명",   { shade: true, bold: true, center: true }),
    cell("분석",     { span: 3 }),
    cell("작성일자", { shade: true, bold: true, center: true }),
    cell("",         { span: 3 }),
    cell(""),
    cell(""),
  ]});

  return new Table({
    width: { size: TABLE_W, type: WidthType.DXA },
    columnWidths: COLS,
    rows: [
      metaRow1,
      metaRow2,
      metaRow3,
      buildHeaderRow(),
      ...requirements.map(buildReqRow),
    ]
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Malgun Gothic", size: 20 } } }
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: 12240 },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN }
      }
    },
    children: [
      new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: "1.1 사용자 요구사항 정의서", font: "Malgun Gothic", size: 28, bold: true })]
      }),
      new Paragraph({ children: [new TextRun({ text: "【산출물 양식】", font: "Malgun Gothic", size: 20, bold: true })] }),
      new Paragraph({ children: [new TextRun({ text: "■ 제·개정 이력", font: "Malgun Gothic", size: 20 })] }),
      buildRevisionTable(),
      new Paragraph({ children: [new TextRun({ text: "" })] }),
      buildMainTable(reqs),
    ]
  }]
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('/home/claude/requirements_definition.docx', buf);
  console.log('완료');
});

window.MathJax = {
  // Nạp sẵn extension boldsymbol: để autoload lười thì \boldsymbol hiện thành chữ đỏ
  loader: { load: ["[tex]/boldsymbol"] },
  tex: {
    packages: { "[+]": ["boldsymbol"] },
    // \llbracket, \rrbracket thuộc gói stmaryrd, MathJax 3 không có sẵn (hiện chữ đỏ)
    macros: {
      llbracket: "\\mathopen{[\\![}",
      rrbracket: "\\mathclose{]\\!]}"
    },
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    ignoreHtmlClass: ".*|",
    processHtmlClass: "arithmatex"
  }
};

// Material dùng instant navigation: render lại toán mỗi khi đổi trang
document$.subscribe(() => {
  MathJax.startup.output.clearCache();
  MathJax.typesetClear();
  MathJax.texReset();
  MathJax.typesetPromise();
});

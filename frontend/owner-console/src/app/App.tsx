import { Button } from "../components/ui/Button";
import { Panel } from "../components/ui/Panel";
import { StatusTag } from "../components/ui/StatusTag";

const navigationItems = ["总览", "信号", "交易", "复盘"] as const;

export function App() {
  return (
    <>
      <header className="top-navigation">
        <div className="app-container top-navigation__inner">
          <span className="brand-mark">BRC OWNER</span>
          <nav className="primary-navigation" aria-label="一级导航">
            {navigationItems.map((item, index) => (
              <a
                className="primary-navigation__link"
                href="/"
                aria-current={index === 0 ? "page" : undefined}
                key={item}
              >
                {item}
              </a>
            ))}
          </nav>
          <div className="runtime-summary" aria-label="运行摘要">
            <span className="tabular-number">PROD</span>
            <span className="runtime-summary__separator" aria-hidden="true">
              ·
            </span>
            <StatusTag tone="success">正常</StatusTag>
            <span className="runtime-summary__separator runtime-summary__time" aria-hidden="true">
              ·
            </span>
            <span className="runtime-summary__time tabular-number">数据时间 --</span>
          </div>
        </div>
      </header>

      <main className="app-container owner-main">
        <div className="baseline-toolbar">
          <h1 className="baseline-title">UI System B</h1>
          <Button>刷新当前页</Button>
        </div>
        <Panel title="界面基础">
          <div className="primitive-row">
            <span className="text-secondary">环境</span>
            <span className="tabular-number">PROD</span>
            <span className="text-secondary">状态</span>
            <StatusTag tone="success">正常</StatusTag>
            <span className="text-secondary optional-detail">控制高度</span>
            <span className="tabular-number optional-detail">32 px</span>
          </div>
        </Panel>
      </main>
    </>
  );
}

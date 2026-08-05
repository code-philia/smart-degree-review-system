import { Link } from 'react-router-dom';
import RoleAwareHomeMenu from '../auth/RoleAwareHomeMenu';

const userModules = ['学生端', '导师端', '学院端', '学校端'];
const engineModules = ['数据库存储', '多级权限管理', 'AI 模型库'];
const coreModules = [
  { title: '规范性检测', description: '格式、错别字与语言规范检查' },
  { title: '论文查重', description: '基于本地规则与持久化材料比对' },
  { title: '创新性分析', description: '新颖性与方法创新辅助分析' },
  { title: '论文润色', description: '语言优化与表达改进建议' },
  { title: 'AI 智能评阅', description: '本地可解释评阅意见与修改建议' },
];

function ArrowUp() {
  return (
    <div className="flex h-14 items-center justify-center" aria-hidden="true">
      <div className="relative h-12 w-1 bg-black">
        <div className="absolute -top-1 left-1/2 h-0 w-0 -translate-x-1/2 border-x-[10px] border-b-[16px] border-x-transparent border-b-black" />
      </div>
    </div>
  );
}

function SealMark() {
  return (
    <div className="flex h-24 w-24 items-center justify-center rounded-full border-[6px] border-[#B00020] text-[#B00020]">
      <div className="flex h-16 w-16 flex-col items-center justify-center rounded-full border-2 border-[#B00020] text-center">
        <span className="text-xs font-black tracking-widest">AI</span>
        <span className="text-[10px] font-bold">DEGREE</span>
      </div>
    </div>
  );
}

function HomePage() {
  return (
    <main className="min-h-screen bg-white text-slate-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10">
        <header className="flex flex-col items-center gap-4 text-center">
          <SealMark />
          <div>
            <p className="text-sm font-semibold tracking-[0.4em] text-[#B00020]">LOCAL EXPLAINABLE REVIEW</p>
            <h1 className="mt-2 text-3xl font-black tracking-tight md:text-5xl">智慧学位 AI 评阅辅助系统</h1>
            <p className="mt-3 max-w-3xl text-base leading-7 text-slate-600">
              面向学生、导师、学院管理人员和学校管理人员的单端口 B/S 学位论文辅助系统。
            </p>
          </div>
        </header>

        <RoleAwareHomeMenu />

        <div className="flex flex-col items-center" aria-label="系统架构图">
          <section className="w-full border border-[#9CCC65] bg-[#D50000] px-6 py-7 text-white">
            <h2 className="text-center text-3xl font-black md:text-4xl">用户层</h2>
            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-4">
              {userModules.map((module) => (
                <div key={module} className="border border-[#8FADE8] px-6 py-4 text-center text-2xl font-bold">
                  {module}
                </div>
              ))}
            </div>
          </section>

          <ArrowUp />

          <section className="w-full border border-[#8FADE8] bg-[#4B79C9] px-6 py-8 text-white">
            <h2 className="text-center text-3xl font-black md:text-4xl">核心功能层</h2>
            <div className="mt-7 grid grid-cols-1 gap-5 md:grid-cols-6">
              {coreModules.map((module, index) => (
                <div
                  key={module.title}
                  className={`border border-[#8FADE8] px-5 py-5 text-center ${
                    index < 3 ? 'md:col-span-2' : 'md:col-span-3'
                  }`}
                >
                  <h3 className="text-2xl font-black">{module.title}</h3>
                  <p className="mt-2 text-base font-medium leading-6">{module.description}</p>
                  {module.title === 'AI 智能评阅' ? (
                    <Link className="mt-4 inline-flex rounded bg-white px-4 py-2 text-sm font-black text-[#1f3f63]" to="/ai-review">发起评阅</Link>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <ArrowUp />

          <section className="w-full border border-[#8FADE8] bg-[#334155] px-6 py-7 text-white">
            <h2 className="text-center text-3xl font-black md:text-4xl">数据算法引擎层</h2>
            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
              {engineModules.map((module) => (
                <div key={module} className="border border-[#8FADE8] px-6 py-4 text-center text-2xl font-bold">
                  {module}
                </div>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

export default HomePage;

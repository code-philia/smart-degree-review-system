import { Link } from 'react-router-dom';
import { LinkButton } from '../components/ui';

function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 py-20 text-center">
      <p className="text-sm font-black text-brand-500">404</p>
      <h1 className="text-2xl font-black text-slate-900">页面不存在</h1>
      <p className="text-sm leading-6 text-slate-500">
        你访问的地址不存在，或该功能尚未在当前试点版本中提供。可以返回工作台继续操作。
      </p>
      <div className="mt-2 flex gap-3">
        <LinkButton to="/">返回工作台</LinkButton>
        <Link
          className="inline-flex h-10 items-center rounded-lg border border-slate-300 px-4 text-sm font-bold text-slate-600"
          to="/about"
        >
          查看系统说明
        </Link>
      </div>
    </div>
  );
}

export default NotFoundPage;

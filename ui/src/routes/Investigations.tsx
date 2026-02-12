import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

interface Investigation {
  investigation_id: string;
  title: string;
}

const Investigations: React.FC = () => {
  const [list, setList] = useState<Investigation[]>([]);
  const [title, setTitle] = useState('');

  const fetch = async () => {
    const res = await api.get('/api/v1/investigations/');
    setList(res.data);
  };

  const create = async () => {
    if (!title) return;
    await api.post('/api/v1/investigations/', { title });
    setTitle('');
    fetch();
  };

  useEffect(() => {
    fetch();
  }, []);

  return (
    <div className="dark:text-white">
      <h2 className="text-2xl mb-4">Investigations</h2>
      <div className="mb-4 flex">
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="New investigation title"
          className="border rounded px-2 py-1 mr-2 flex-1 bg-white dark:bg-gray-700 dark:text-white dark:border-gray-600"
        />
        <button onClick={create} className="bg-blue-600 text-white px-3 rounded">
          Create
        </button>
      </div>
      <ul className="list-disc pl-5">
        {list.map(inv => (
          <li key={inv.investigation_id}>
            <Link to={`/investigation/${inv.investigation_id}`} className="text-blue-600 underline">
              {inv.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default Investigations;

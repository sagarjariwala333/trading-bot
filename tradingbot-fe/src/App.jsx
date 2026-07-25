import Navbar from './components/Navbar'
import Footer from './components/Footer'
import Dashboard from './pages/Dashboard'

function App() {
  return (
    <div className="min-h-screen bg-[#070a13] dark:bg-[#070a13] text-slate-100 dark:text-slate-100 flex flex-col transition-colors duration-300">
      <Navbar />
      <main className="flex-1 w-full pt-[64px] flex flex-col">
        <Dashboard />
      </main>
      <Footer />
    </div>
  )
}

export default App

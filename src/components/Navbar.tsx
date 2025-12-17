import { useState, useEffect } from 'react';
import { Menu, X, Home, Info, Briefcase, DollarSign, Mail } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { Button } from './ui/button';
import cortexLogo from '@/assets/cortexcloud-logo.jpg';

const Navbar = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const location = useLocation();

  const navLinks = [
    { label: 'About', href: '/about', icon: Info },
    { label: 'Services', href: '/services', icon: Briefcase },
    { label: 'Pricing', href: '/pricing', icon: DollarSign },
    { label: 'Contact', href: '/contact', icon: Mail },
  ];

  const mobileNavLinks = [
    { label: 'Home', href: '/', icon: Home },
    ...navLinks,
  ];

  const isActive = (href: string) => location.pathname === href;

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Close menu when route changes
  useEffect(() => {
    setIsMenuOpen(false);
  }, [location.pathname]);

  return (
    <>
      <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled ? 'glass-strong shadow-lg' : 'bg-background/50 backdrop-blur-md'
      }`}>
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 md:h-20">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2 min-w-0">
              <img 
                src={cortexLogo} 
                alt="CortexCloud" 
                className="h-9 md:h-12 w-auto rounded flex-shrink-0"
              />
            </Link>

            {/* Desktop Navigation */}
            <div className="hidden md:flex items-center gap-8">
              {navLinks.map((link) => (
                <Link
                  key={link.label}
                  to={link.href}
                  className={`transition-colors duration-200 text-sm font-medium ${
                    isActive(link.href)
                      ? 'text-primary'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {link.label}
                </Link>
              ))}
            </div>

            {/* CTA Button */}
            <div className="hidden md:block">
              <Button variant="primary" size="lg" asChild>
                <Link to="/contact">Book a Call</Link>
              </Button>
            </div>

            {/* Mobile Menu Button */}
            <button
              className="md:hidden p-3 -mr-2 text-foreground touch-manipulation"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-label="Toggle menu"
            >
              {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Menu Overlay */}
        {isMenuOpen && (
          <div 
            className="md:hidden fixed inset-0 top-16 bg-background/95 backdrop-blur-xl z-40"
            onClick={() => setIsMenuOpen(false)}
          >
            <div className="container mx-auto px-4 py-6" onClick={e => e.stopPropagation()}>
              <div className="space-y-2">
                {mobileNavLinks.map((link) => (
                  <Link
                    key={link.label}
                    to={link.href}
                    className={`flex items-center gap-4 px-4 py-4 rounded-xl transition-all duration-200 touch-manipulation ${
                      isActive(link.href)
                        ? 'bg-primary/10 text-primary'
                        : 'text-foreground hover:bg-secondary active:bg-secondary/80'
                    }`}
                    onClick={() => setIsMenuOpen(false)}
                  >
                    <link.icon size={22} />
                    <span className="text-lg font-medium">{link.label}</span>
                  </Link>
                ))}
              </div>
              <div className="mt-6 px-4">
                <Button variant="primary" className="w-full h-14 text-lg" asChild>
                  <Link to="/contact" onClick={() => setIsMenuOpen(false)}>
                    Book a Call
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 glass-strong border-t border-border safe-area-bottom">
        <div className="flex items-center justify-around h-16 pb-safe">
          {mobileNavLinks.slice(0, 5).map((link) => (
            <Link
              key={link.label}
              to={link.href}
              className={`flex flex-col items-center justify-center gap-1 py-2 px-3 min-w-[64px] touch-manipulation transition-colors ${
                isActive(link.href)
                  ? 'text-primary'
                  : 'text-muted-foreground active:text-foreground'
              }`}
            >
              <link.icon size={22} />
              <span className="text-[10px] font-medium">{link.label}</span>
            </Link>
          ))}
        </div>
      </nav>
    </>
  );
};

export default Navbar;

import { useState, useEffect } from 'react';
import { Home, Info, Briefcase, DollarSign, Mail } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { Button } from './ui/button';
import cortexLogo from '@/assets/cortexcloud-logo.jpg';

const Navbar = () => {
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

            {/* CTA Button - visible on all screen sizes */}
            <Button variant="primary" size="lg" asChild className="text-sm md:text-base px-4 md:px-6">
              <Link to="/contact">Book a Call</Link>
            </Button>
          </div>
        </div>
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

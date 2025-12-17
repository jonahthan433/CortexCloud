import { useState } from 'react';
import { Mail, Phone, MapPin, Send, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';

const Contact = () => {
  const { toast } = useToast();
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    message: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast({
      title: "Message sent!",
      description: "We'll get back to you within 24 hours.",
    });
    setFormData({ name: '', email: '', company: '', message: '' });
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const contactInfo = [
    {
      icon: Mail,
      title: 'Email Us',
      content: 'hello@cortexcloud.ai',
      description: 'We respond within 24 hours',
    },
    {
      icon: Phone,
      title: 'Call Us',
      content: '+1 (555) 123-4567',
      description: 'Mon-Fri, 9am-6pm EST',
    },
    {
      icon: MapPin,
      title: 'Visit Us',
      content: '123 AI Street, Tech City',
      description: 'San Francisco, CA 94102',
    },
    {
      icon: Clock,
      title: 'Business Hours',
      content: 'Mon-Fri: 9am-6pm',
      description: 'Sat-Sun: Closed',
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <main className="pt-24 md:pt-32">
        {/* Hero Section */}
        <section className="py-16 md:py-24 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-hero" />
          <div className="absolute top-1/2 left-1/3 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
          
          <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
            <div className="max-w-3xl mx-auto text-center space-y-6">
              <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                Contact Us
              </span>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold font-display">
                Let's Start a <span className="text-gradient">Conversation</span>
              </h1>
              <p className="text-lg text-muted-foreground">
                Have questions about our AI solutions? Ready to transform your business? We'd love to hear from you.
              </p>
            </div>
          </div>
        </section>

        {/* Contact Section */}
        <section className="py-16 md:py-24 relative">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8">
            <div className="grid lg:grid-cols-2 gap-12">
              {/* Contact Form */}
              <div className="order-2 lg:order-1">
                <div className="glass-strong rounded-2xl p-8">
                  <h2 className="text-2xl font-bold font-display mb-6">Send us a message</h2>
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="grid sm:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <label htmlFor="name" className="text-sm font-medium">Name</label>
                        <Input
                          id="name"
                          name="name"
                          placeholder="John Doe"
                          value={formData.name}
                          onChange={handleChange}
                          required
                          className="glass border-border/50 focus:border-primary"
                        />
                      </div>
                      <div className="space-y-2">
                        <label htmlFor="email" className="text-sm font-medium">Email</label>
                        <Input
                          id="email"
                          name="email"
                          type="email"
                          placeholder="john@company.com"
                          value={formData.email}
                          onChange={handleChange}
                          required
                          className="glass border-border/50 focus:border-primary"
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="company" className="text-sm font-medium">Company</label>
                      <Input
                        id="company"
                        name="company"
                        placeholder="Your company name"
                        value={formData.company}
                        onChange={handleChange}
                        className="glass border-border/50 focus:border-primary"
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="message" className="text-sm font-medium">Message</label>
                      <Textarea
                        id="message"
                        name="message"
                        placeholder="Tell us about your project or ask us anything..."
                        rows={5}
                        value={formData.message}
                        onChange={handleChange}
                        required
                        className="glass border-border/50 focus:border-primary resize-none"
                      />
                    </div>
                    <Button variant="primary" size="lg" className="w-full">
                      Send Message <Send size={18} className="ml-2" />
                    </Button>
                  </form>
                </div>
              </div>

              {/* Contact Info */}
              <div className="order-1 lg:order-2 space-y-6">
                <div className="space-y-4">
                  <h2 className="text-2xl font-bold font-display">Get in touch</h2>
                  <p className="text-muted-foreground">
                    Whether you're ready to start your AI journey or just exploring options, our team is here to help.
                  </p>
                </div>

                <div className="grid sm:grid-cols-2 gap-4">
                  {contactInfo.map((info, index) => (
                    <div key={index} className="glass-strong rounded-xl p-6 hover:-translate-y-1 transition-transform duration-300">
                      <div className="w-10 h-10 rounded-lg bg-gradient-primary flex items-center justify-center mb-4">
                        <info.icon size={20} className="text-primary-foreground" />
                      </div>
                      <h3 className="font-bold font-display mb-1">{info.title}</h3>
                      <p className="text-foreground">{info.content}</p>
                      <p className="text-sm text-muted-foreground">{info.description}</p>
                    </div>
                  ))}
                </div>

                {/* Book a Call CTA */}
                <div className="relative mt-8">
                  <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-20 blur-xl" />
                  <div className="relative glass-strong rounded-2xl p-8 text-center">
                    <h3 className="text-xl font-bold font-display mb-2">Prefer a conversation?</h3>
                    <p className="text-muted-foreground mb-4">
                      Schedule a free 30-minute consultation with our AI experts.
                    </p>
                    <Button variant="primary" size="lg">
                      Book a Free Call
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default Contact;

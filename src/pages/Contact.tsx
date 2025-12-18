import { Mail, Phone, MapPin, Clock, MessageSquare, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Contact = () => {
  const contactInfo = [
    {
      icon: Mail,
      title: 'Email Us',
      content: 'hello@cortexcloud.ai',
      description: 'We respond within 24 hours',
      href: 'mailto:hello@cortexcloud.ai',
    },
    {
      icon: Phone,
      title: 'Call Us',
      content: '+1 (555) 123-4567',
      description: 'Mon-Fri, 9am-6pm EST',
      href: 'tel:+15551234567',
    },
    {
      icon: MapPin,
      title: 'Visit Us',
      content: '123 AI Street, Tech City',
      description: 'San Francisco, CA 94102',
      href: '#',
    },
    {
      icon: Clock,
      title: 'Business Hours',
      content: 'Mon-Fri: 9am-6pm',
      description: 'Sat-Sun: Closed',
      href: '#',
    },
  ];

  const supportChannels = [
    {
      icon: MessageSquare,
      title: 'Live Chat',
      description: 'Get instant answers from our AI-powered support assistant.',
      action: 'Start Chat',
    },
    {
      icon: Calendar,
      title: 'Schedule a Call',
      description: 'Book a free 30-minute consultation with our AI experts.',
      action: 'Book Now',
    },
  ];

  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-20 md:pt-32">
          {/* Hero Section */}
          <section className="py-12 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute top-1/2 left-1/3 w-64 md:w-96 h-64 md:h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-3xl mx-auto text-center space-y-4 md:space-y-6">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                    Contact Us
                  </span>
                  <h1 className="text-mobile-hero font-bold font-display">
                    Let's Start a <span className="text-gradient">Conversation</span>
                  </h1>
                  <p className="text-mobile-body text-muted-foreground">
                    Have questions about our AI solutions? Ready to transform your business? We'd love to hear from you.
                  </p>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Contact Info Grid */}
          <section className="py-12 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="text-center mb-12">
                  <h2 className="text-mobile-title font-bold font-display mb-4">Get in Touch</h2>
                  <p className="text-muted-foreground text-mobile-body max-w-2xl mx-auto">
                    Whether you're ready to start your AI journey or just exploring options, our team is here to help.
                  </p>
                </div>
              </FadeIn>

              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-16">
                {contactInfo.map((info, index) => (
                  <FadeIn key={index} delay={index * 0.1}>
                    <a 
                      href={info.href}
                      className="glass-strong rounded-2xl p-6 md:p-8 hover:-translate-y-2 transition-all duration-300 block touch-manipulation active:scale-95 text-center group"
                    >
                      <div className="w-14 h-14 rounded-xl bg-gradient-primary flex items-center justify-center mx-auto mb-4 group-hover:shadow-button transition-shadow">
                        <info.icon size={24} className="text-primary-foreground" />
                      </div>
                      <h3 className="font-bold font-display text-lg mb-2">{info.title}</h3>
                      <p className="text-foreground text-base mb-1">{info.content}</p>
                      <p className="text-sm text-muted-foreground">{info.description}</p>
                    </a>
                  </FadeIn>
                ))}
              </div>

              {/* Support Channels */}
              <div className="grid md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                {supportChannels.map((channel, index) => (
                  <FadeIn key={index} delay={0.4 + index * 0.1}>
                    <div className="relative group">
                      <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-20 blur-xl group-hover:opacity-30 transition-opacity" />
                      <div className="relative glass-strong rounded-2xl p-8 text-center">
                        <div className="w-16 h-16 rounded-xl bg-gradient-primary flex items-center justify-center mx-auto mb-4">
                          <channel.icon size={28} className="text-primary-foreground" />
                        </div>
                        <h3 className="text-xl font-bold font-display mb-2">{channel.title}</h3>
                        <p className="text-muted-foreground mb-6">{channel.description}</p>
                        <Button variant="primary" size="lg" className="w-full sm:w-auto">
                          {channel.action}
                        </Button>
                      </div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* Map/Location Section */}
          <section className="py-12 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="glass-strong rounded-2xl p-8 md:p-12 text-center">
                  <h2 className="text-mobile-title font-bold font-display mb-4">
                    Our <span className="text-gradient">Headquarters</span>
                  </h2>
                  <p className="text-muted-foreground text-mobile-body max-w-2xl mx-auto mb-8">
                    Located in the heart of San Francisco's tech district, we're always happy to welcome visitors. 
                    Schedule an appointment to tour our AI innovation lab.
                  </p>
                  <div className="bg-muted/30 rounded-xl h-64 md:h-80 flex items-center justify-center">
                    <div className="text-center">
                      <MapPin size={48} className="text-primary mx-auto mb-4" />
                      <p className="text-lg font-medium">123 AI Street, Tech City</p>
                      <p className="text-muted-foreground">San Francisco, CA 94102</p>
                    </div>
                  </div>
                </div>
              </FadeIn>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default Contact;